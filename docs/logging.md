# 日志

项目使用 Python 标准库 logging，并在应用边界统一配置结构化字段、输出格式、request ID 和驱动。默认是单行 JSON 写 stdout；Console 会把 stream 日志强制写 stderr，以保护命令结果的 stdout 协议。

## 1. 最小配置

```dotenv
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_ACCESS_ENABLED=true
LOG_ACCESS_EXCLUDE_ROUTES=["/health"]
LOG_ACTIVE_HANDLERS=["stdout"]
LOG_HANDLERS={"stdout":{"driver":"stream","stream":"stdout"}}
```

本地人工阅读可改为：

```dotenv
LOG_FORMAT=text
```

两种格式携带相同语义字段；生产日志采集通常更适合 JSON。

## 2. 公共字段

每条格式化日志包含：

| 字段 | 说明 |
| --- | --- |
| `timestamp` | 当前本地时区的 ISO 8601 时间，精确到毫秒并带 offset |
| `level` | `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL` |
| `logger` | logger 名称 |
| `service` | `APP_NAME` |
| `environment` | `APP_ENV` |
| `service_version` | `APP_VERSION` |
| `message` | 人类可读消息 |
| `request_id` | 有 HTTP 请求上下文时附加 |
| `event` | 稳定、可查询的事件名 |
| `details` | 该事件的结构化细节 |
| `exception` | `type`、`message`、`stacktrace`，仅异常日志出现 |

JSON 示例：

```json
{"timestamp":"2026-09-01T10:00:00.000+08:00","level":"INFO","logger":"app.interfaces.http.access","service":"fast-api-scaff","environment":"local","service_version":"3.0.3","message":"HTTP request completed","request_id":"...","event":"http.request.completed","details":{"method":"GET","route":"/api/v1/users","status_code":200,"duration_ms":12.3,"client_ip":"127.0.0.1"}}
```

业务和基础设施日志应把稳定分类放在 `event`，把可检索维度放在 `details`，不要把所有信息拼进 message。

## 3. 记录结构化日志

```python
import logging
from enum import StrEnum

from app.infrastructure.logging.record import log_extra


class ExampleLogEvent(StrEnum):
    COMPLETED = "example.completed"


logger = logging.getLogger("app.contexts.example")
logger.info(
    "Example completed",
    extra=log_extra(ExampleLogEvent.COMPLETED, example_id="123"),
)
```

使用 `app.*` logger 才会继承项目为应用日志设置的级别与 handler。事件名建议采用稳定的点分层级，如 `context.action.outcome`；不要把 ID 或动态文本放进 event 名。

异常应使用 `logger.exception()` 或显式 `exc_info=True`，以产生 `exception` 结构：

```python
try:
    ...
except Exception:
    logger.exception("Example failed", extra=log_extra("example.failed"))
    raise
```

记录之后继续抛出，除非当前边界明确负责恢复；不要用日志代替错误处理。

## 4. Logger 级别与 Uvicorn

配置结果：

- `app` logger 使用 `LOG_LEVEL`；
- `uvicorn` logger 使用 `LOG_LEVEL`；
- `uvicorn.access` 被禁用，避免与项目访问日志重复；
- `sqlalchemy` 默认 WARNING；
- root logger 默认 WARNING；
- 已存在的第三方 logger 不会被全局禁用。

所以 `LOG_LEVEL=DEBUG` 主要控制 `app` 与 `uvicorn`，并不保证所有第三方库都输出 DEBUG。若要调整特定第三方 logger，应在日志装配中显式配置并评估噪声。

## 5. HTTP 访问日志

开启 `LOG_ACCESS_ENABLED` 后，每个完成或失败的 HTTP 请求记录事件 `http.request.completed`，details 包含：

- `method`；
- 匹配后的 route 模板，而不是包含具体 ID 的 URL；
- `status_code`；
- `duration_ms`；
- `client_ip`；
- 失败时的 `failed` 与 `failure_type`。

级别规则：

- 正常 2xx/3xx：INFO；
- 4xx：WARNING；
- 5xx 或未处理异常：ERROR；
- 请求取消：WARNING，并使用有效状态 499。

`LOG_ACCESS_EXCLUDE_ROUTES` 默认排除成功的 `/health`，降低探针噪声。但被排除路由一旦失败，仍会记录，避免静默丢失故障。

route 记录模板如 `/api/v1/users/{user_id}`，降低指标基数。未匹配路由可能没有 route 值。

## 6. Request ID

日志 handler 上的 `RequestContextFilter` 在记录进入 handler 时读取当前 HTTP 上下文，并补充 `request_id`。这意味着同一个请求内 controller、application 和 infrastructure 的日志都可被关联，而这些层不必依赖 FastAPI request。

Console 和启动/关闭阶段没有 HTTP 上下文，日志自然不含 request ID。不要用空字符串伪造 ID；无上下文时省略字段语义更清楚。

如果引入消息队列或 Scheduler，应建立独立 correlation/job ID 上下文，而不是假装它们有 HTTP request ID。

## 7. 应用生命周期日志

HTTP lifespan 产生：

- `application.starting`；
- `application.started`；
- `application.start_failed`；
- `application.stopping`；
- `application.stopped`；
- `application.stop_failed`。

资源层还记录数据库资源创建/关闭和失败事件。启动失败时 runtime 会尝试关闭已经构建的容器，日志顺序可用于判断失败发生在配置、容器启动还是关闭阶段。

## 8. 数据库日志

每个 Engine 注册查询计时事件：

- `database.resource.created/closed`；
- `database.resource.create_failed/close_failed`；
- `database.query.completed`；
- `database.query.slow`；
- `database.query.failed`。

`DB_CONNECTIONS__<NAME>__SLOW_QUERY_MS` 控制慢查询阈值；设为 0 表示不判定慢查询。普通成功查询只有在该连接 `ECHO=true` 时记录。失败查询始终记录摘要。

查询 details 包含 connection、duration、operation、statement ID 和 executemany。默认隐藏 SQL 参数；Engine 创建也启用 `hide_parameters=True`。当 `ECHO=true` 时项目事件会包含 SQL statement，同时 SQLAlchemy 自身也可能输出更多信息，生产开启前必须评估敏感信息和日志体积。

`statement_id` 是归一化 SQL 的短哈希，用于聚合相同查询，不是安全校验值，也不能还原 SQL。

## 9. HTTP 与 Console 的输出差异

| 宿主 | stream 配置为 stdout 时 | 原因 |
| --- | --- | --- |
| HTTP | 仍写 stdout | 适合容器日志采集 |
| Console | 改写到 stderr | stdout 保留给 JSON 命令结果 |

因此同一 `sample.env` 可以同时服务两种宿主。Console 重定向示例：

```bash
uv run python -m app.interfaces.console users list 1>result.json 2>command.log
```

不要绕过项目配置给 Console 新增直接写 stdout 的日志 handler，否则会破坏这个契约。

## 10. Handler 与驱动

当前内置驱动只有 `stream`：

```json
{
  "driver": "stream",
  "stream": "stdout"
}
```

`stream` 只能是 `stdout` 或 `stderr`。至少启用一个 handler；激活列表不能重复；每个激活名称必须在 `LOG_HANDLERS` 中定义；驱动不能覆盖核心保留字段 `formatter` 和 `filters`。

同时输出两个流在多数场景会产生重复日志，不建议把相同级别无过滤地写 stdout 和 stderr。需要按级别分流时，应先设计过滤器和采集规则，而不是仅激活两个 handler。

## 11. 扩展日志驱动

1. 定义严格配置模型；
2. 实现 `LoggingDriverBuilder`，返回标准库 dictConfig handler 片段；
3. 不设置由核心负责的 `formatter` 和 `filters`；
4. 在组合位置注册 driver；
5. 验证 JSON/Text 格式、request ID、异常堆栈和关闭行为；
6. 考虑网络 handler 的阻塞、缓冲、背压和进程退出丢日志；
7. 同步 `sample.env`、[配置参考](configuration.md)与本章。

远程日志传输更适合由 stdout + 部署侧采集器完成。若应用进程直连远端日志服务，必须避免在事件循环中阻塞，并明确失败是否影响业务请求。

## 12. 敏感信息规则

禁止记录：

- 密码、数据库连接串中的秘密；
- token、Cookie、Authorization header；
- 完整身份证号、银行卡等敏感个人数据；
- 无必要的完整请求/响应体；
- SQL 参数和未经审查的原始驱动异常文本对外响应。

可以记录稳定 ID、字段名、约束名、错误类型、耗时和状态。需要调试敏感字段时也应脱敏、限时并有明确删除/恢复步骤。

## 13. 常见问题

| 症状 | 检查项 |
| --- | --- |
| 启动提示至少启用一个 Handler | `LOG_ACTIVE_HANDLERS` 不能为空 |
| 激活 handler 没有对应配置 | JSON 名称是否完全一致 |
| Console 输出不是合法 JSON | 是否有代码直接 print 或第三方日志写 stdout |
| `/health` 没访问日志 | 默认排除；失败仍会记录 |
| 业务日志没有 request ID | 是否在 HTTP 请求上下文内、是否使用已配置 handler |
| 同一请求有两条访问日志 | 是否又启用了 `uvicorn.access` 或代理重复采集 |
| 看不到普通 SQL | 默认只记录慢/失败查询；目标连接 `ECHO` 是否开启 |
| 日志量突然增大 | `LOG_LEVEL`、数据库 ECHO、访问日志排除和重复 handler |
| 时间 offset 不正确 | 宿主 `TZ` 和进程重启 |

跨组件排查见[故障排查](troubleshooting.md)。
