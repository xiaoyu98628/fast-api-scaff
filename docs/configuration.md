# 配置参考

配置由 `pydantic-settings` 从项目根目录 `.env` 和进程环境变量读取。进程环境变量优先于 `.env`；未知字段会被忽略；配置对象创建后不可变，并由 `load_settings()` 在当前进程内缓存。

导入配置模块不会读取或校验环境变量。HTTP、Console 和 Worker 顶层入口均在导入时通过 `load_settings()` 显式创建各组配置并初始化各自的日志；因此即使 Console 或 Worker 只请求 `--help`，也会先校验完整配置。手动构造 `Settings` 时，未提供的认证、HTTP、向量和日志配置由默认值工厂在实例化时创建。默认值工厂的 `_env_file=None` 只跳过 `.env`，仍读取进程环境变量；显式注入这些配置时不会调用对应工厂。

## 1. 命名和嵌套规则

不同配置组使用不同前缀：

| 配置组 | 前缀 | 示例 |
| --- | --- | --- |
| 应用 | `APP_` | `APP_NAME` |
| 认证 | `AUTH_` | `AUTH_SESSION_TTL_SECONDS` |
| 日志 | `LOG_` | `LOG_LEVEL` |
| CORS | `CORS_` | `CORS_ALLOW_ORIGINS` |
| HTTP 出站 | `HTTP_` | `HTTP_TIMEOUT__CONNECT` |
| 数据库 | `DB_` | `DB_CONNECTIONS__MAIN__DRIVER` |
| 缓存 | `CACHE_` | `CACHE_CONNECTIONS__SESSION__DRIVER` |
| 向量存储 | `VECTOR_` | `VECTOR_CONNECTIONS__KNOWLEDGE__DRIVER` |

双下划线 `__` 表示嵌套字典。连接名不区分业务语义，由组合根按名字选择：

```dotenv
DB_CONNECTIONS__MAIN__DRIVER=sqlite
CACHE_CONNECTIONS__SESSION__DRIVER=redis
```

列表、元组、集合和字典使用 JSON：

```dotenv
CORS_ALLOW_ORIGINS=["https://admin.example.com","https://app.example.com"]
LOG_ACTIVE_HANDLERS=["stdout"]
LOG_HANDLERS={"stdout":{"driver":"stream","stream":"stdout"}}
```

布尔值建议统一使用 `true`/`false`。密码会进入 `SecretStr`，错误信息隐藏输入值，但这不等于日志和外部工具永远不会泄露秘密；不要打印完整配置对象，也不要提交真实 `.env`。

## 2. 应用配置

认证配置使用独立的 `AuthSettings`，通过 `settings.auth` 访问：

| 变量 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `AUTH_SESSION_TTL_SECONDS` | `int` | `3600` | 1–2592000 秒；登录时按本地无时区 datetime 确定过期时间，修改配置只影响新会话 |

会话固定存放在用户上下文的 `main` 数据库，且不使用 `CACHE_DEFAULT_TTL`。详见[认证](authentication.md)。

| 变量 | 类型 | 默认值           | 约束与说明 |
| --- | --- |------------------| --- |
| `APP_NAME` | `str` | `fast-api-scaff` | 应用名称 |
| `APP_VERSION` | `str` | `1.0.0`          | 应用版本 |
| `APP_ENV` | `str` | `local`          | 环境标识，不会自动切换其他配置 |
| `APP_DEBUG` | `bool` | `false`          | 应用调试标识；不等同于 Uvicorn `--reload` |
| `APP_SERVICE_CODE` | `str` | `001`            | 必须是 3 位数字，作为统一响应码的服务段 |

`APP_PORT` 出现在 `sample.env` 和 Compose 端口映射中，但不是 `AppSettings` 字段。直接运行 Uvicorn 时仍由命令行 `--port` 决定监听端口；Compose 使用 `${APP_PORT:-8000}` 映射宿主端口。

最终响应码由三位 HTTP status、三位服务码和四位局部业务码组成。例如 HTTP 404、服务码 `001` 与用户不存在 `1001` 组合成 `4040011001`。不要通过更改服务码表达 HTTP 状态；三个分段承担不同语义。

## 3. 时区配置

| 变量 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `TZ` | 时区名称 | `Asia/Shanghai` | 进程本地时区；当前领域时间采用本地无时区值 |

`TZ` 不是 Pydantic 配置模型字段，而是进程/系统时区约定。必须在 HTTP、Console、迁移和部署环境保持一致。已有业务数据产生后不要直接改变时区；如必须改变，应先明确旧数据的语义并执行数据迁移。

## 4. 日志配置

| 变量 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `LOG_LEVEL` | 枚举 | `INFO` | `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL` |
| `LOG_FORMAT` | 枚举 | `json` | `json` 或 `text` |
| `LOG_ACCESS_ENABLED` | `bool` | `true` | 是否装配 HTTP 访问日志中间件 |
| `LOG_ACCESS_EXCLUDE_ROUTES` | JSON 字符串集合 | `["/health"]` | 完整请求路径的精确匹配集合，每项必须以 `/` 开头；失败请求不会因排除而静默 |
| `LOG_ACTIVE_HANDLERS` | JSON 字符串元组 | `["stdout"]` | 激活的 handler 名称 |
| `LOG_HANDLERS` | JSON 对象 | stdout stream | handler 定义；当前内置驱动为 `stream` |

内置 stream handler：

```dotenv
LOG_HANDLERS={"stdout":{"driver":"stream","stream":"stdout"},"stderr":{"driver":"stream","stream":"stderr"}}
LOG_ACTIVE_HANDLERS=["stdout"]
```

handler 定义、驱动和输出协议详见[日志](logging.md)。配置中的 handler 名必须存在，驱动参数必须符合实现，否则宿主初始化日志时失败。

## 5. CORS 配置

| 变量 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `CORS_ALLOW_ORIGINS` | JSON 字符串列表 | `["*"]` | 允许的来源 |
| `CORS_ALLOW_METHODS` | JSON 字符串列表 | `["*"]` | 允许的方法 |
| `CORS_ALLOW_HEADERS` | JSON 字符串列表 | `["*"]` | 允许的请求头 |
| `CORS_ALLOW_CREDENTIALS` | `bool` | `false` | 是否允许 Cookie/认证凭据 |
| `CORS_EXPOSE_HEADERS` | JSON 字符串列表 | `["*"]` | 浏览器 JS 可读取的响应头 |
| `CORS_MAX_AGE` | `int` | `600` | 预检缓存秒数，必须大于等于 0 |

当 `CORS_ALLOW_CREDENTIALS=true` 时，`CORS_ALLOW_ORIGINS` 不能包含 `*`，配置模型会拒绝启动。生产环境建议显式列出来源、方法和请求头，不要把默认通配符当成安全策略。

## 6. HTTP 出站配置

HTTP 出站配置在 `load_settings()` 时严格校验，普通请求和流式请求共享阶段超时，但使用独立连接池。

阶段超时：

| 变量 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `HTTP_TIMEOUT__CONNECT` | `float` | `3.0` | 建立 TCP/TLS 连接，正数秒 |
| `HTTP_TIMEOUT__READ` | `float` | `10.0` | 等待响应数据，正数秒 |
| `HTTP_TIMEOUT__WRITE` | `float` | `10.0` | 发送请求数据，正数秒 |

普通连接池使用 `HTTP_POOL__*`，流式连接池使用 `HTTP_STREAM_POOL__*`：

| 后缀 | 普通池默认值 | 流式池默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `TIMEOUT` | `5.0` | `10.0` | 等待连接池容量，正数秒 |
| `MAX_CONNECTIONS` | `100` | `100` | 总连接数，至少 1 |
| `MAX_KEEPALIVE_CONNECTIONS` | `20` | `10` | keep-alive 容量，0 到总连接数 |
| `KEEPALIVE_EXPIRY` | `30.0` | `30.0` | 空闲连接过期时间，正数秒 |

其他配置：

| 变量 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `HTTP_VERIFY` | `bool` | `true` | 验证服务端 TLS 证书；生产不应关闭 |
| `HTTP_FOLLOW_REDIRECTS` | `bool` | `false` | 是否自动跟随重定向 |
| `HTTP_TRUST_ENV` | `bool` | `false` | 是否读取 `HTTP_PROXY`、`HTTPS_PROXY`、`NO_PROXY` 等环境变量 |
| `HTTP_POOL_WARNING_RATIO` | `float` | `0.8` | 单个池的进行中请求达到容量比例时记录压力告警，范围为 `(0, 1]` |
| `HTTP_MAX_RESPONSE_BYTES` | `int` | `10485760` | 普通响应解压后的最大缓冲字节数，至少为 1；不限制流式响应 |

连接池延迟到首次出站请求时创建。配置不包含具体上游地址、认证或自动重试策略；这些属于使用该上游的上下文适配器。调用方式、错误和流生命周期见[HTTP 出站请求](outbound-http.md)。

## 7. 数据库全局配置

| 变量 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DB_DEFAULT` | `str | null` | `null` | 未显式传连接名时使用的默认连接 |
| `DB_CONNECTIONS` | 嵌套对象 | `{}` | 按名称保存连接原始定义 |

连接定义会在该连接第一次被获取时解析和严格校验，不是统一在进程读取 `.env` 时全部校验。因此一个从未使用的错误数据库连接可能不会阻止 `/health`，但会在首次访问时失败。

### 7.1 公共字段

| 后缀 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- |
| `DRIVER` | 枚举 | 无 | 必填；`mysql`、`postgresql`、`pgsql`、`sqlite` |
| `ECHO` | `bool` | `false` | SQLAlchemy SQL echo |
| `SLOW_QUERY_MS` | `int` | `500` | 慢查询阈值毫秒，必须大于等于 0 |

### 7.2 MySQL

以连接名 `MAIN` 为例：

| 变量 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- |
| `DB_CONNECTIONS__MAIN__HOST` | `str` | 无 | 非空 |
| `...__PORT` | `int` | `3306` | 1–65535 |
| `...__DATABASE` | `str` | 无 | 非空 |
| `...__USERNAME` | `str` | 无 | 非空 |
| `...__PASSWORD` | `str` | 无 | 非空 |
| `...__CHARSET` | `str` | `utf8mb4` | 非空 |
| `...__POOL_SIZE` | `int` | `10` | 至少 1 |
| `...__MAX_OVERFLOW` | `int` | `20` | 至少 0 |
| `...__POOL_PRE_PING` | `bool` | `true` | 借出连接前检测 |
| `...__POOL_RECYCLE` | `int` | `3600` | 秒，至少 -1 |

使用 `mysql` 驱动时底层异步驱动为项目已安装的 asyncmy。

### 7.3 PostgreSQL

字段与 MySQL 的连接池字段一致，但默认端口为 `5432`，没有 `CHARSET` 字段。`DRIVER` 可写 `postgresql` 或 `pgsql`；底层异步驱动为 asyncpg。

### 7.4 SQLite

| 后缀 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DRIVER` | 字面值 | 无 | 必须为 `sqlite` |
| `DATABASE` | `str` | 无 | `:memory:`、绝对路径或相对 `storage/` 的路径 |
| `ECHO` | `bool` | `false` | SQL echo |
| `SLOW_QUERY_MS` | `int` | `500` | 慢查询阈值 |

SQLite 不接受 MySQL/PostgreSQL 的连接池字段。连接模型使用 `extra="forbid"`，拼错字段或为驱动添加不支持的字段会在首次取连接时失败。

完整数据库行为见[数据库](database.md)。

## 8. 缓存全局配置

| 变量 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `CACHE_DEFAULT` | `str | null` | `null` | 默认缓存连接名 |
| `CACHE_NAMESPACE` | `str` | 空 | 配置任一连接后必须非空 |
| `CACHE_DEFAULT_TTL` | `int | null` | `300` | 秒；环境变量只能写正整数；`None` 仅可由代码构造 Settings 时显式传入 |
| `CACHE_CONNECTIONS` | 嵌套对象 | `{}` | 按名称保存连接定义 |

与数据库不同，所有缓存连接定义会在 `CacheManager` 构造时校验。因此无效的未使用缓存连接也会阻止 HTTP/Console 宿主构建容器。远程网络连接仍是延迟建立。

### 8.1 公共字段

每个连接都需要 `DRIVER`，并可配置 `KEY_PREFIX`。最终 key 为：

```text
{CACHE_NAMESPACE}:{KEY_PREFIX}:{业务 key}
```

空 prefix 会被省略。namespace/prefix 不能包含空白、控制字符，也不能以冒号开头或结尾。

### 8.2 Redis

| 后缀 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- |
| `DRIVER` | 字面值 | 无 | `redis` |
| `HOST` | `str` | 无 | 非空 |
| `PORT` | `int` | `6379` | 1–65535 |
| `DATABASE` | `int` | `0` | 至少 0 |
| `USERNAME` | `str | null` | `null` | 有值时非空 |
| `PASSWORD` | `str | null` | `null` | 有值时非空 |
| `SSL` | `bool` | `false` | 是否使用 TLS |
| `MAX_CONNECTIONS` | `int` | `10` | 至少 1 |
| `CONNECT_TIMEOUT` | `float` | `5.0` | 正数秒 |
| `READ_TIMEOUT` | `float` | `5.0` | 正数秒 |

### 8.3 Memcached

| 后缀 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- |
| `DRIVER` | 字面值 | 无 | `memcached` |
| `HOST` | `str` | 无 | 非空 |
| `PORT` | `int` | `11211` | 1–65535 |
| `USERNAME` / `PASSWORD` | `str | null` | `null` | 必须同时配置或同时省略 |
| `SSL` | `bool` | `false` | 是否使用 TLS |
| `MIN_CONNECTIONS` | `int` | `1` | 至少 1，不能大于 max |
| `MAX_CONNECTIONS` | `int` | `10` | 至少 1 |
| `CONNECT_TIMEOUT` | `float` | `5.0` | 正数秒 |
| `READ_TIMEOUT` | `float` | `5.0` | 正数秒 |
| `BLOCKING_TIMEOUT` | `float` | `5.0` | 正数秒 |

完整语义见[缓存](cache.md)。

## 9. 向量存储配置

| 变量 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `VECTOR_DEFAULT` | `str | null` | `null` | 未显式传连接名时使用的默认向量连接 |
| `VECTOR_CONNECTIONS` | 嵌套对象 | `{}` | 按名称保存连接定义 |

全部向量连接会在 `VectorStoreManager` 构造时按 `DRIVER/MODE` 严格校验，因此无效的未使用定义也会阻止容器构建。SDK 客户端、远程访问和本地文件/目录仍延迟到首次 `get()`。

### 9.1 公共远程字段

| 后缀 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `HOST` | `str` | 无 | 只允许主机名或 IP，不能包含协议、端口或路径 |
| `PORT` | `int` | 由驱动决定 | 1–65535 |
| `USERNAME` / `PASSWORD` | `str | null` | `null` | 必须同时配置或同时省略 |
| `SSL` | `bool` | `false` | `true` 时使用 HTTPS/TLS |

没有公开 `URL` 字段。配置显式保留 host、port、ssl 和认证，驱动内部才组装 URI 或 SDK node config。

### 9.2 Milvus

| 后缀 | 本地默认值/约束 | 远程默认值/约束 |
| --- | --- | --- |
| `DRIVER` | `milvus` | `milvus` |
| `MODE` | `local` | `remote` |
| `PATH` | 必填；文件路径，绝对路径或相对 `storage/` | 不支持 |
| `HOST` / `PORT` | 不支持 | host 必填；port=`19530` |
| `DATABASE` | 不支持 | `default` |
| `USERNAME` / `PASSWORD` | 不支持 | 可选，必须成对 |
| `SSL` | 不支持 | `false` |
| `TIMEOUT` | `10.0`，正数秒 | `10.0`，正数秒 |

### 9.3 Chroma

| 后缀 | 本地默认值/约束 | 远程默认值/约束 |
| --- | --- | --- |
| `DRIVER` | `chroma` | `chroma` |
| `MODE` | `local` | `remote` |
| `PATH` | 必填；目录路径，绝对路径或相对 `storage/` | 不支持 |
| `HOST` / `PORT` | 不支持 | host 必填；port=`8000` |
| `TENANT` | `default_tenant` | `default_tenant` 或 Cloud tenant |
| `DATABASE` | `default_database` | `default_database` 或 Cloud database |
| `USERNAME` / `PASSWORD` | 不支持 | 可选的前置代理 Basic Auth，必须成对 |
| `API_KEY` | 不支持 | 可选的 Chroma Cloud token，不能与 Basic Auth 同时配置 |
| `SSL` | 不支持 | `false` |

Chroma 1.x 自托管服务没有内置认证；`USERNAME/PASSWORD` 只用于明确配置了 Basic Auth 的前置代理。当前 Chroma SDK 没有与其他两个驱动等价的客户端请求超时参数，因此 Chroma 配置不接受 `TIMEOUT`，避免出现配置存在但不生效的假契约。

### 9.4 Elasticsearch

Elasticsearch 仅支持 `MODE=remote`，默认端口为 `9200`。除公共远程字段外：

| 后缀 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `VERIFY_CERTS` | `bool` | `true` | 是否校验证书；生产应保持开启 |
| `CA_CERTS` | `str | null` | `null` | CA 证书文件路径 |
| `CONNECTIONS_PER_NODE` | `int` | `10` | 每节点连接数，至少 1 |
| `MAX_RETRIES` | `int` | `3` | SDK 最大重试次数，至少 0 |
| `RETRY_ON_TIMEOUT` | `bool` | `true` | 是否重试超时 |
| `TIMEOUT` | `float` | `10.0` | 请求超时，正数秒 |

完整连接、调用和数据约束见[向量存储](vector.md)。

## 10. 校验与连接时机

| 阶段 | 会发生什么 | 不会发生什么 |
| --- | --- | --- |
| `load_settings()` | 读取并校验应用、日志、CORS、HTTP 出站配置，读取数据库/缓存/向量原始字典 | 不创建 HTTP、数据库或向量资源，不连接远程缓存 |
| 构建容器 | 构建管理器；校验所有缓存和向量定义 | 不访问 HTTP 上游或数据库网络，不主动 ping 缓存/向量服务 |
| 首次 HTTP `request/stream` | 创建普通与流式连接池并访问目标上游 | 不会探测其他上游，不会自动重试 |
| 首次数据库 `get/session` | 校验目标定义、创建 Engine/Session 工厂 | 不保证每个已配置连接都可用 |
| 首次缓存 `get/set/ping` | 创建目标缓存资源并访问后端 | 不会自动切换到其他连接或后端 |
| 首次向量 `get/ping/CRUD/search` | 创建目标 SDK 客户端；本地模式按需创建数据；远程驱动在创建或首次操作时访问服务 | 不会探测其他向量连接或自动切换驱动 |
| 关闭宿主 | 逆序关闭已初始化资源 | 未初始化资源不会被无意义连接 |

这解释了为什么“应用能启动”不等于“所有依赖都健康”。生产就绪检查应主动验证业务必需的连接，但不要把非关键依赖随意绑进基础 `/health`，否则会改变健康语义。

## 11. 修改配置后的操作

- HTTP：重启 Uvicorn 进程；`--reload` 是否监视 `.env` 取决于运行器行为，不应作为配置热更新契约。
- Console：每次命令是新进程，重新执行即可。
- 测试：若进程内修改环境变量，需要清理 `load_settings()` 缓存；测试代码应显式处理，生产代码不要动态改环境。
- 数据库结构：修改模型配置不等于迁移，仍需创建并应用 Alembic revision。
- `TZ`：视为数据语义变更，不是普通重启配置。

## 12. 配置安全与禁止做法

- 不提交真实 `.env`、密码或连接串；`sample.env` 只能放示例值。
- 不在业务层直接读取 `os.environ`；配置只应在组合根解析并注入。
- 不用 `APP_ENV` 隐式拼接大量魔法默认值；部署差异应显式可审计。
- 不依赖 `/health` 推断数据库和缓存已经连接。
- 不依赖 `/health` 推断向量服务可用，也不把本地向量目录交给多个进程共享。
- 不通过 `HTTP_VERIFY=false` 长期绕过生产 TLS 证书问题。
- 不假设基础 HTTP 客户端会自动重试或把 4xx/5xx 转成异常。
- 不通过改变 `DB_DEFAULT` 猜测用户上下文会切库；当前组合明确指定 `main`。
- 不为本地开发配置与部署环境不同的缓存驱动；测试隔离应使用测试目录内的 Fake。
- 不把 `LOG_LEVEL=DEBUG` 当作生产故障的长期方案，尤其不要记录密码、令牌和完整个人数据。

配置报错时，先对照 `sample.env` 和本章字段，再阅读[故障排查](troubleshooting.md)。

## 13. 队列与 Worker

HTTP 不启动消费者。新增配置无队列连接默认值；`QUEUE_DEFAULT` 留空应省略该变量，而不是写空字符串。

`QUEUE_CONNECTIONS__<NAME>` 中的 `<NAME>` 是连接名，用来选择后端、集群、认证信息和消费组；`QUEUE_DEFAULT` 选择的也是连接名，不是逻辑队列名。每个连接的 `default_queue` 是未显式传入队列时使用的逻辑队列。发布时的 `queue=` 和 Worker 的 `--queue` 可以在同一连接上选择其他逻辑队列，因此一个连接不需要为每个业务队列重复配置。后端、集群、认证信息或消费组不同时，则应配置不同的命名连接。

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| QUEUE_DEFAULT | None | 默认连接名，不是逻辑队列名 |
| QUEUE_CONNECTIONS | {} | 命名连接，可用双下划线配置多个连接及其字段 |
| QUEUE_MAX_MESSAGE_BYTES | 1048576 | 完整编码信封的字节上限，最小 256 |
| QUEUE_FAILED__DATABASE | main | 失败记录数据库连接；Worker 与 Console 使用前必须配置 |
| QUEUE_WORKER__CONCURRENCY | 4 | 1–1024 个执行槽，Kafka 同分区仍串行 |
| QUEUE_WORKER__SHUTDOWN_TIMEOUT_SECONDS | 30 | 取消在途任务前的等待时间 |

所有连接包含 driver、default_queue（default，1–200 个非空白字符）、publish_timeout（10 秒）。驱动特有字段如下；不支持的额外字段会被拒绝。

| driver | 字段 |
| --- | --- |
| redis | host 必填；port=6379；database=0；username/password 可选；ssl=false；max_connections=10；connect_timeout=5；group=workers；prefix=queue:；lease_seconds=120（至少 3 秒）；command_timeout=10（至少 2 秒） |
| kafka | bootstrap_servers 非空列表；group=workers；security_protocol=PLAINTEXT；sasl_mechanism=PLAIN；username/password 可选；max_poll_interval_ms=300000 |
| rabbitmq | host 必填；port=5672；virtual_host=/；username/password=guest；ssl=false；connect_timeout=5 |

Kafka security_protocol 可选 PLAINTEXT、SSL、SASL_PLAINTEXT、SASL_SSL；SASL 模式需要 username/password，mechanism 支持 PLAIN、SCRAM-SHA-256、SCRAM-SHA-512。Kafka 保留 bootstrap_servers 列表以支持多个 Broker。Redis 和 RabbitMQ 使用独立的主机、端口及认证字段；ssl=true 时使用系统 CA。Redis command_timeout 控制普通命令与消费阻塞读取的 socket 超时，和仅约束发布调用的 publish_timeout 相互独立。Redis 工作队列在 QueueJob 的 `handle()` 完成或失败记录落库后原子执行 XACK + XDEL，不保留已完成的 Stream 历史。

完整环境示例见 `sample.env`，其中 `redis`、`kafka` 和 `rabbitmq` 三个命名连接可同时存在，`QUEUE_DEFAULT=redis` 仅指定默认使用 Redis 连接。使用方式见[队列](queue.md)与[Worker](worker.md)。Settings 新增 queue，Worker 参数位于 `queue.worker`，ApplicationContainer 新增 queues。构建容器校验连接字段但不连接；失败存储数据库名称在 Worker 或 Console 使用前校验。资源按使用创建，关闭后不允许重新获取。
