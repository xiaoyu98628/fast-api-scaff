# 配置参考

配置由 `pydantic-settings` 从项目根目录 `.env` 和进程环境变量读取。进程环境变量优先于 `.env`；未知字段会被忽略；配置对象创建后不可变，并由 `load_settings()` 在当前进程内缓存。

## 1. 命名和嵌套规则

不同配置组使用不同前缀：

| 配置组 | 前缀 | 示例 |
| --- | --- | --- |
| 应用 | `APP_` | `APP_NAME` |
| 日志 | `LOG_` | `LOG_LEVEL` |
| CORS | `CORS_` | `CORS_ALLOW_ORIGINS` |
| 数据库 | `DB_` | `DB_CONNECTIONS__MAIN__DRIVER` |
| 缓存 | `CACHE_` | `CACHE_CONNECTIONS__LOCAL__DRIVER` |

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

| 变量 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `APP_NAME` | `str` | `fast-api-scaff` | 应用名称 |
| `APP_VERSION` | `str` | `3.0.3` | 应用版本 |
| `APP_ENV` | `str` | `local` | 环境标识，不会自动切换其他配置 |
| `APP_DEBUG` | `bool` | `false` | 应用调试标识；不等同于 Uvicorn `--reload` |
| `APP_SERVICE_CODE` | `str` | `001` | 必须是 3 位数字，作为统一响应码的服务段 |

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
| `LOG_ACCESS_EXCLUDE_ROUTES` | JSON 字符串集合 | `["/health"]` | 每项必须以 `/` 开头；失败请求不会因排除而静默 |
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

## 6. 数据库全局配置

| 变量 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DB_DEFAULT` | `str | null` | `null` | 未显式传连接名时使用的默认连接 |
| `DB_CONNECTIONS` | 嵌套对象 | `{}` | 按名称保存连接原始定义 |

连接定义会在该连接第一次被获取时解析和严格校验，不是统一在进程读取 `.env` 时全部校验。因此一个从未使用的错误数据库连接可能不会阻止 `/health`，但会在首次访问时失败。

### 6.1 公共字段

| 后缀 | 类型 | 默认值 | 约束 |
| --- | --- | --- | --- |
| `DRIVER` | 枚举 | 无 | 必填；`mysql`、`postgresql`、`pgsql`、`sqlite` |
| `ECHO` | `bool` | `false` | SQLAlchemy SQL echo |
| `SLOW_QUERY_MS` | `int` | `500` | 慢查询阈值毫秒，必须大于等于 0 |

### 6.2 MySQL

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

### 6.3 PostgreSQL

字段与 MySQL 的连接池字段一致，但默认端口为 `5432`，没有 `CHARSET` 字段。`DRIVER` 可写 `postgresql` 或 `pgsql`；底层异步驱动为 asyncpg。

### 6.4 SQLite

| 后缀 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DRIVER` | 字面值 | 无 | 必须为 `sqlite` |
| `DATABASE` | `str` | 无 | `:memory:`、绝对路径或相对 `storage/` 的路径 |
| `ECHO` | `bool` | `false` | SQL echo |
| `SLOW_QUERY_MS` | `int` | `500` | 慢查询阈值 |

SQLite 不接受 MySQL/PostgreSQL 的连接池字段。连接模型使用 `extra="forbid"`，拼错字段或为驱动添加不支持的字段会在首次取连接时失败。

完整数据库行为见[数据库](database.md)。

## 7. 缓存全局配置

| 变量 | 类型 | 默认值 | 约束与说明 |
| --- | --- | --- | --- |
| `CACHE_DEFAULT` | `str | null` | `null` | 默认缓存连接名 |
| `CACHE_NAMESPACE` | `str` | 空 | 配置任一连接后必须非空 |
| `CACHE_DEFAULT_TTL` | `int | null` | `300` | 秒；环境变量只能写正整数；`None` 仅可由代码构造 Settings 时显式传入 |
| `CACHE_CONNECTIONS` | 嵌套对象 | `{}` | 按名称保存连接定义 |

与数据库不同，所有缓存连接定义会在 `CacheManager` 构造时校验。因此无效的未使用缓存连接也会阻止 HTTP/Console 宿主构建容器。远程网络连接仍是延迟建立。

### 7.1 公共字段

每个连接都需要 `DRIVER`，并可配置 `KEY_PREFIX`。最终 key 为：

```text
{CACHE_NAMESPACE}:{KEY_PREFIX}:{业务 key}
```

空 prefix 会被省略。namespace/prefix 不能包含空白、控制字符，也不能以冒号开头或结尾。

### 7.2 Redis

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

### 7.3 Memcached

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

### 7.4 Memory

```dotenv
CACHE_CONNECTIONS__LOCAL__DRIVER=memory
CACHE_CONNECTIONS__LOCAL__KEY_PREFIX=local
```

Memory 没有网络参数。数据仅存在于当前进程内，进程重启即丢失，多 worker 之间也不共享。

完整语义见[缓存](cache.md)。

## 8. 校验与连接时机

| 阶段 | 会发生什么 | 不会发生什么 |
| --- | --- | --- |
| `load_settings()` | 读取应用、日志、CORS、数据库/缓存原始字典 | 不创建数据库 Engine，不连接远程缓存 |
| 构建容器 | 构建管理器；校验所有缓存定义 | 不访问数据库网络，不主动 ping 缓存 |
| 首次数据库 `get/session` | 校验目标定义、创建 Engine/Session 工厂 | 不保证每个已配置连接都可用 |
| 首次缓存 `get/set/ping` | 创建目标缓存资源并访问后端 | 不会自动回退到 Memory |
| 关闭宿主 | 逆序关闭已初始化资源 | 未初始化资源不会被无意义连接 |

这解释了为什么“应用能启动”不等于“所有依赖都健康”。生产就绪检查应主动验证业务必需的连接，但不要把非关键依赖随意绑进基础 `/health`，否则会改变健康语义。

## 9. 修改配置后的操作

- HTTP：重启 Uvicorn 进程；`--reload` 是否监视 `.env` 取决于运行器行为，不应作为配置热更新契约。
- Console：每次命令是新进程，重新执行即可。
- 测试：若进程内修改环境变量，需要清理 `load_settings()` 缓存；测试代码应显式处理，生产代码不要动态改环境。
- 数据库结构：修改模型配置不等于迁移，仍需创建并应用 Alembic revision。
- `TZ`：视为数据语义变更，不是普通重启配置。

## 10. 配置安全与禁止做法

- 不提交真实 `.env`、密码或连接串；`sample.env` 只能放示例值。
- 不在业务层直接读取 `os.environ`；配置只应在组合根解析并注入。
- 不用 `APP_ENV` 隐式拼接大量魔法默认值；部署差异应显式可审计。
- 不依赖 `/health` 推断数据库和缓存已经连接。
- 不通过改变 `DB_DEFAULT` 猜测用户上下文会切库；当前组合明确指定 `main`。
- 不把 Memory 当作多进程共享缓存或持久存储。
- 不把 `LOG_LEVEL=DEBUG` 当作生产故障的长期方案，尤其不要记录密码、令牌和完整个人数据。

配置报错时，先对照 `sample.env` 和本章字段，再阅读[故障排查](troubleshooting.md)。
