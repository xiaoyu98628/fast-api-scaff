# 故障排查

排查原则：先确认“实际运行的宿主、配置和资源”，再根据错误发生阶段向内缩小。不要因为 `/health` 成功就跳过数据库/缓存检查，也不要因为看到 500 就先扩大异常捕获。

## 1. 五分钟诊断

从项目根目录执行：

```bash
uv run python -m app.interfaces.console app info
uv run alembic -c database/main/alembic.ini current
uv run python -m pytest -q tests/test_architecture.py
git status --short
```

然后检查：

1. `app info` 的环境、时区和连接名是否符合预期；
2. main migration 是否在 head；
3. HTTP/Console 是否由同一个项目虚拟环境运行；
4. 错误日志中的 `event`、`details`、`request_id` 和最内层异常；
5. 当前 `.env` 是否刚修改但进程未重启；
6. 宿主机与容器中的地址语义是否混淆。

## 2. 症状速查表

| 症状 | 最可能原因 | 优先动作 |
| --- | --- | --- |
| `/health` 成功，用户接口失败 | 健康检查不访问数据库 | 查 `main`、迁移、真实连接日志 |
| `main` 未配置 | 嵌套键拼错或缺失 | 检查 `DB_CONNECTIONS__MAIN__...` |
| 改 `DB_DEFAULT` 没切库 | 用户上下文固定使用 main | 查看 composition，按架构修改而非只改 env |
| `no such table: users` | 未迁移或迁移到另一个 SQLite 文件 | 用正确 ini/current，确认解析后的文件路径 |
| 启动时报缓存配置错误 | 所有缓存定义启动校验 | 检查包括未使用连接在内的全部 CACHE 配置 |
| 启动正常，首次 Redis 操作失败 | 远程连接延迟建立 | 检查 DNS/端口/TLS/认证/超时并 ping |
| Docker 内连不上 `127.0.0.1` | 地址指向应用容器自身 | 使用 Compose 服务名或宿主可达地址 |
| Console JSON 被日志污染 | 有输出写入 stdout | 日志走配置/ stderr，移除 print |
| 重复用户名返回 500 | 约束 marker 未识别 | 核对物理约束名和驱动错误详情 |
| 更新时后写覆盖先写 | 当前无乐观并发控制 | 按业务引入 version/条件更新/锁 |
| 时间相差 8 小时或无 offset | 本地无时区语义/TZ 不一致 | 统一 TZ，勿盲目转换已有数据 |
| CORS 凭据配置无法启动 | origins 同时含 `*` | 显式列出可信来源 |
| `page`/`limit` 请求返回 422 | 页码从 1 开始，每页范围为 1–1000；旧 `offset`/`page_size` 不再接受 | 修正参数并查看 validation data |
| DELETE 解析 JSON 失败 | 204 没有响应体 | 客户端按 status 处理 |
| `f` 没有生效 | Base64/URL/JSON 格式不合法 | 用项目 encode 函数生成并确认它替换查询串 |
| 多 worker 缓存不一致 | 使用 Memory | 换共享后端，Memory 仅单进程 |
| cache set 报 bytes 错误 | 未显式编码 | 使用 Text/Json codec |
| key 超长或含空白 | 最终 key 违反跨驱动规则 | 检查 namespace+prefix+业务 key UTF-8 长度 |
| Alembic autogenerate 无变化 | Model 未注册 | 更新 `database/main/model_registry.py` |
| 普通 SQL 没日志 | ECHO 默认 false | 临时开启目标连接 ECHO 并评估敏感信息 |
| request ID 不在日志 | 不在 HTTP 上下文或日志未走配置 handler | 查中间件顺序和 logger/handler |
| 出站请求等待连接池超时 | 目标池容量耗尽或流未关闭 | 查普通/流式池配置、并发和 `async with` |
| 出站请求未走预期代理 | `HTTP_TRUST_ENV=false` | 明确启用后检查 proxy/NO_PROXY 环境变量 |

## 3. 配置加载失败

### 现象

进程启动或 Console 命令立即输出 `配置 ...`，退出码为 1。

### 检查

- JSON 值必须是合法 JSON，字符串使用双引号；
- 双下划线表示嵌套，单下划线不能替代；
- `APP_SERVICE_CODE` 必须是三位数字；
- CORS 凭据模式下 origin 不能含 `*`；
- 日志 active handler 非空、无重复且有定义；
- Memcached username/password 同时出现或同时省略；
- 端口、pool、timeout 和 TTL 满足数值范围。

修改 `.env` 后重启当前宿主。`load_settings()` 在同一进程缓存，测试里动态改环境变量不会自动刷新。

未知顶层环境变量会被忽略，所以拼错某些变量不一定立即报“extra field”；它可能表现为默认值仍在生效。用 `app info` 和针对性配置测试核实，不要只看 `.env` 文件内容。

## 4. HTTP 无法启动或访问

### 端口问题

直接运行 Uvicorn：

```bash
uv run uvicorn app.main:app --reload --port 8000
```

`APP_PORT` 不会自动改变这个命令的监听端口；它主要供 Compose 宿主端口映射使用。确认没有其他进程占用端口，并区分容器内部固定 8000 与宿主映射端口。

### Debug 行为

`APP_DEBUG=true` 时，未处理异常会继续抛给调试错误处理，而不是由项目中间件稳定转换成通用 500。只在受控开发环境使用，不要用生产响应差异判断业务错误映射失效。

### 路由 404/405

确认路径包含 `/api/v1`，方法与路由表一致。框架 404/405 会被统一错误响应包装；业务用户不存在也是 404，但业务 code 不同。

### 请求校验 422

读取响应 `data` 的 `location` 和 `message`：它区分 path/query/body。更新接口是完整 PUT；多余字段因 `extra="forbid"` 被拒绝。

## 5. 数据库问题

### `/health` 正常但业务失败

这是延迟初始化的预期结果。按顺序检查：

```bash
uv run alembic -c database/main/alembic.ini current
uv run python -m app.interfaces.console users list
```

Console 和 HTTP 都失败，通常是共享数据库/业务层；只 HTTP 失败则检查 HTTP schema、依赖或中间件；只 Console 失败则检查参数、输出和 Console 日志边界。

### SQLite 文件不一致

`DB_CONNECTIONS__MAIN__DATABASE=data/database.sqlite` 解析为项目 `storage/data/database.sqlite`，不是终端下的 `data/database.sqlite`。迁移环境与应用都读取 main 配置；确认没有不同工作目录、环境覆盖或绝对路径指向另一文件。

### 数据库可达性

- 宿主名和端口；
- 容器 DNS 与网络；
- 数据库是否已创建；
- 用户权限与密码；
- MySQL charset/PostgreSQL SSL 等部署要求；
- 连接池总量是否超过服务端限制；
- 查看 `database.query.failed` 的 connection、operation、error code。

### 唯一冲突映射

应用预检查不能覆盖并发竞态，数据库约束是最终防线。若已知 username/email 重复返回 500：

1. 查数据库实际约束名；
2. 查驱动 `IntegrityError.orig` 可见信息；
3. 对照 UoW marker；
4. 为该方言补测试后再调整映射。

不要用“出现 IntegrityError 就 username conflict”的宽泛修复，它会掩盖其他数据缺陷。

## 6. Alembic 问题

所有命令必须指定配置：

```bash
uv run alembic -c database/main/alembic.ini current
```

若提示找不到 script location 或配置，确认从项目根目录执行。若 autogenerate 漏模型，检查 `database/main/model_registry.py` 是否显式注册。

生成结果异常时不要直接 upgrade：先检查是否把重命名识别成 drop/add，是否缺少数据回填，是否使用目标数据库方言。SQLite 通过 batch mode 处理部分 DDL，与生产方言生成结果可能不同。

## 7. 缓存问题

### 配置阶段失败

缓存与数据库的校验时机不同：容器构建时会准备所有缓存定义。即使默认连接是 local，一个错误的 session Redis 配置也可能阻止启动。检查每个 `CACHE_CONNECTIONS__...`，或者从 `.env` 删除暂不需要的连接定义。

### 网络阶段失败

首次资源创建/操作才触发远程访问。检查：

- Redis/Memcached 服务是否可达；
- TLS 是否与服务端一致；
- username/password 组合；
- Redis database 编号；
- connect/read/blocking timeout；
- 容器中的 hostname；
- 通过 `CacheManager.ping(name)` 做真实验证。

脚手架不会自动回退，业务若允许回源应在上下文缓存适配器显式记录并实现。

### TTL 与 key

- TTL 只能是正整数、默认枚举或永不过期枚举；
- Memcached 超过 30 天会转绝对时间，检查系统时钟；
- Memory 数据在进程重启/worker 间不共享；
- 最终 key UTF-8 最长 250 字节；
- codec 变更后旧值可能解码失败，使用 schema 版本和有限 TTL。

## 8. HTTP 出站问题

### 连接、超时与状态码

- `HttpPoolTimeoutError` 表示等待连接池容量超时，区分普通池与流式池配置；
- `HttpTimeoutError` 表示连接、读或写阶段超时；
- `HttpTransportError` 表示网络或传输协议失败；
- `HttpResponseTooLargeError` 表示普通响应解压后超过 `HTTP_MAX_RESPONSE_BYTES`，需要核对上游契约或改用带业务限制的流式消费；
- 4xx/5xx 不会自动抛异常，应由具体上游适配器按协议检查；
- 基础客户端不会自动重试，不能通过盲目重发 POST 掩盖超时。

连接池容量超时会产生 `http.outbound.pool.timeout` WARNING，并带有 `pool=standard` 或 `pool=stream`；同一次调用随后还会产生对应请求/流失败事件。任务取消使用 `request.cancelled` 或 `stream.cancelled` INFO 事件，不应按上游故障告警。

若只有流式请求耗尽容量，确认每次都使用 `async with container.http.stream(...)`，并检查消费任务是否能够响应取消。普通与流式请求使用不同连接池，调整时不要只改 `HTTP_POOL__*`。

### TLS、代理与依赖升级

生产应保持 `HTTP_VERIFY=true` 并修复证书链。`HTTP_TRUST_ENV=false` 时不会读取进程代理变量；启用后同时检查 `HTTP_PROXY`、`HTTPS_PROXY` 和 `NO_PROXY`，避免内部地址误走代理。

客户端不读取或修改 HTTPX2/httpcore2 私有连接池状态。升级 HTTPX2 或 httpcore2 后仍必须运行 `tests/outbound_http/test_http11_cancellation.py` 和全量验证，确认流式与缓冲请求取消后单连接池可以继续服务后续请求。

日志默认不包含 path、query、header 或 body。用稳定 `operation` 定位调用，再结合已脱敏的上游错误和分布式追踪信息排查；不要为了临时诊断记录 Authorization 或完整响应体。

若请求目标来自 HTTP/Console 输入，不要把用户提供的完整 URL 直接交给出站客户端。目标 scheme、host 和 port 必须来自受信任配置，业务输入只能作为经过校验和编码的 path/query 数据，否则可能形成 SSRF。

## 9. Console 问题

### 退出码 2

属于 Typer 用法错误：查看 `--help`，检查 option 名、必填值和数值范围。

### 退出码 1

stderr 中会有业务、配置或基础设施错误。单独重定向：

```bash
uv run python -m app.interfaces.console users list 1>result.json 2>error.log
```

若 stdout 为空是正常失败行为，不要把 stderr 当 JSON 解析。

### 命令未出现

- 模块是否位于 `app/interfaces/console/commands/`；
- 类是否直接/间接继承 `ConsoleCommand`；
- 类是否定义在被扫描模块自身；
- 是否为抽象类；
- 是否存在重复 group/name 或不一致 group_help；
- import 顶层是否抛错或执行外部副作用。

## 10. 日志问题

### 没有日志

- active handler 是否非空；
- handler 名是否有定义；
- logger 是否在 `app`/`uvicorn` 下且级别足够；
- 第三方 logger 可能受 root WARNING 限制；
- HTTP access 是否被关闭或路由被排除。

### 重复日志

- 不要额外启用 `uvicorn.access`；
- 检查是否激活多个指向同一流的 handler；
- 检查部署采集器是否同时读取 stdout 与容器文件；
- 自定义 logger 是否 propagate 到已处理的父 logger。

### 时间或 request ID 异常

日志时间是本地 aware 时间，领域数据是本地 naive 时间，两者表现不同但应对应同一 `TZ`。request ID 只在 HTTP 上下文自然存在；Console/启动日志没有是正常行为。

## 11. Docker 问题

当前 `compose.yml` 只启动应用服务。它：

- 从 `.env` 读取配置；
- 把宿主 `${APP_PORT:-8000}` 映射到容器 8000；
- bind mount 项目源码并使用独立 `/app/.venv` volume；
- 运行 Uvicorn `--reload`；
- 不启动数据库或缓存。

若使用 SQLite，相对路径位于 bind mount 的项目 `storage/` 下；检查目录写权限。若使用外部服务，容器内 `127.0.0.1` 不是宿主。若容器不断重启，先用 Compose 日志查看配置/导入/端口错误；当前 `restart: no`，正常情况下不会自动重启。

Dockerfile 的生产默认命令不带 reload，但 Compose 覆盖了它。不要把当前 Compose 直接当生产编排。

## 12. 时间不一致

当前设计要求本地无时区业务时间。常见错误：

- 某个宿主使用 `datetime.now(timezone.utc)`，Domain 会拒绝；
- HTTP 和 Console 的 `TZ` 不同，写出语义不一致的 naive 值；
- 数据库服务器自动转换 timestamp，而模型期待普通 DATETIME；
- 更改 `TZ` 后把旧 naive 数据按新时区解释；
- API 消费方把无 offset 字符串默认当 UTC。

解决前先明确旧值究竟代表哪个时区。不要仅通过加/减 8 小时“修复”表象。跨时区改造必须同步 Domain、时钟、DTO、ORM、迁移和客户端契约。

## 13. 架构测试失败

错误形如：

```text
app/contexts/example/application/service.py:10 imports app.infrastructure.cache.manager
```

修复方向是依赖倒置：在当前 context 的 application/domain 定义窄协议，把具体适配器放 infrastructure，并由 composition 注入。不要把 import 移到函数内部、用动态 import 或 `Any` 绕过检查；那只隐藏依赖，不修复架构。

跨上下文协作也不要直接 import 对方 infrastructure。通过明确的公开应用端口或上层 workflow 协调，并明确事务/一致性边界。

## 14. 仍无法定位时

保留以下最小证据：

- 精确命令、入口和退出码/HTTP status；
- 已脱敏的相关环境变量名和值类型；
- `app info` 输出；
- migration current/head；
- 一条完整结构化错误日志及 request ID；
- 宿主机/容器、目标服务地址和网络关系；
- 最小可复现请求；
- 最近相关 diff。

然后沿[架构说明](architecture.md)的调用链定位责任层。不要先删除缓存、回滚数据库或重置工作区；这些操作可能破坏证据和用户数据。
