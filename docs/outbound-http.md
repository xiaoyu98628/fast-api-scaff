# HTTP 出站请求

项目提供驱动无关的异步 HTTP 出站能力。公共调用方使用 `HttpRequest`、`HttpResponse`、`HttpStreamResponse` 和 `ApplicationContainer.http`；只有 `app.infrastructure.http.drivers.httpx2` 依赖 HTTPX2。普通请求与流式请求使用独立连接池，并随 HTTP 或 Console 宿主的应用容器统一关闭。

## 1. 普通请求

```python
from app.bootstrap.container import ApplicationContainer
from app.infrastructure.http.contracts.request import HttpRequest


async def fetch_profile(container: ApplicationContainer, user_id: str) -> object:
    response = await container.http.request(
        HttpRequest(
            method="GET",
            url=f"https://profiles.example.com/users/{user_id}",
            headers={"Accept": "application/json"},
            operation="profiles.get",
        )
    )

    if response.status_code != 200:
        raise RuntimeError(f"profile upstream returned {response.status_code}")

    return response.json()
```

普通响应会在 `HTTP_MAX_RESPONSE_BYTES` 限制内完整缓冲为 bytes，离开请求方法后仍可安全使用。限制按解压后的实际字节累计，超限抛出 `HttpResponseTooLargeError` 并关闭响应连接。`headers` 保留重复响应头；`header(name)` 返回第一个值，`header_values(name)` 返回全部值。无法预估大小或允许超过该限制的内容必须使用流式接口，并在具体上游适配器中设置自己的总量和处理时限。

基础客户端不会把 4xx/5xx 自动转成异常，因为状态码属于具体上游协议。调用上游的上下文应根据其契约完成状态码、响应 schema 和业务错误映射。

## 2. 流式请求

```python
from app.bootstrap.container import ApplicationContainer
from app.infrastructure.http.contracts.request import HttpRequest


async def consume_events(container: ApplicationContainer) -> None:
    request = HttpRequest(
        method="GET",
        url="https://events.example.com/stream",
        operation="events.consume",
    )

    async with container.http.stream(request) as response:
        if response.status_code != 200:
            body = await response.aread()
            raise RuntimeError(f"event upstream returned {response.status_code}: {body!r}")

        async for chunk in response.aiter_bytes():
            await handle_chunk(chunk)
```

`HttpStreamResponse` 只能在所属 `async with` 内使用。退出上下文会通过 HTTPX2 公开的上下文管理协议释放或关闭底层连接；任务取消时驱动会屏蔽关闭过程的取消。普通请求为了实施响应大小限制，底层同样通过受控流式读取完成，因此也复用这条公开关闭路径。普通与流式请求分池，长连接不会直接占用普通请求池容量。

## 3. 请求字段

`HttpRequest` 支持：

- `method`：会 trim 并转为大写；
- `url`：必须是带有效主机名和端口的 `http`/`https` 绝对地址，显式端口范围为 1～65535；
- `operation`：稳定的低基数操作名，用于日志检索；
- `headers`、`params`；
- `content` 或 `json`，二者不能同时提供；
- `timeout`：可选的单次请求覆盖值，正数秒。

不传 `json` 表示没有 JSON 请求体；显式传入 `json=None` 会发送 JSON `null` 和 `Content-Type: application/json`。这两个状态不会混用。

不要把 token、用户 ID、查询串或完整 URL 放进 `operation`。当前请求 header 使用 mapping，若上游要求重复请求头，应先扩展公共契约并同步驱动与测试。

基础客户端接受绝对 URL，但这不代表 HTTP/Console 用户可以选择目标主机。具体上游适配器必须从受信任配置取得 scheme、host 和 port，只把经过校验、编码的业务值放入 path/query；将用户提交的完整 URL 直接传给客户端会形成 SSRF 风险。

## 4. 超时与连接池

全局阶段超时：

- `HTTP_TIMEOUT__CONNECT`：建立 TCP/TLS 连接；
- `HTTP_TIMEOUT__READ`：等待响应数据；
- `HTTP_TIMEOUT__WRITE`：发送请求数据。

普通池使用 `HTTP_POOL__*`，流式池使用 `HTTP_STREAM_POOL__*`。每个池配置等待容量的 `TIMEOUT`、总连接数、keep-alive 连接数和过期时间。keep-alive 数不能大于总连接数。`HTTP_POOL_WARNING_RATIO` 控制进行中请求达到池容量多少比例时记录一次压力告警；请求数降到阈值以下后，下一次达到阈值会再次告警。

`HttpRequest.timeout` 会覆盖该次请求的所有 HTTPX2 超时阶段，包括等待连接池。若上游需要不同的 connect/read 策略，应通过上游适配器和公共契约显式设计，不要在业务代码中依赖 HTTPX2 类型。

## 5. 错误语义

公共错误层级：

```text
HttpError
├── HttpResponseTooLargeError
└── HttpTransportError
    └── HttpTimeoutError
        └── HttpPoolTimeoutError
```

- 网络、协议和连接失败转为 `HttpTransportError`；
- 阶段超时转为 `HttpTimeoutError`；
- 等待连接池容量超时转为 `HttpPoolTimeoutError`；
- 普通响应解压后超过 `HTTP_MAX_RESPONSE_BYTES` 转为 `HttpResponseTooLargeError`；
- HTTP 4xx/5xx 仍作为正常 `HttpResponse` 返回；
- 调用方任务取消保持原取消异常，不包装成传输错误。

JSON 解码失败、调用参数错误和调用方业务处理异常不属于网络传输错误，不应被宽泛捕获后伪装成 `HttpTransportError`。

## 6. 重试边界

基础客户端不自动重试。自动重试无法在不知道上游协议的情况下判断 POST 是否幂等、是否已经被服务端接受、响应体能否重放，以及退避是否符合限流规则。

确有需要时，在具体上游适配器中按操作实现，并明确：

- 允许重试的方法或幂等键；
- 可重试的传输错误和状态码；
- 最大次数、总时间预算、指数退避和抖动；
- 流式请求是否允许重连以及续传位置；
- 指标、日志和最终错误映射。

## 7. 日志与敏感信息

普通请求记录完成、失败或取消，流式请求记录连接、完成、失败或取消；资源创建、关闭、连接池压力和容量超时也有独立事件。请求日志只包含 method、origin、可选 operation、状态、耗时和响应大小，不记录 path、query、请求/响应体或 header。

池压力和容量超时日志包含 pool、active、peak active、limit、usage、cancelled 与 pool timeout；容量超时还记录 client ID。客户端不读取或修改 HTTPX2/httpcore2 私有连接池状态，避免把诊断能力绑定到第三方内部结构。

任务取消记录 INFO 事件，不会记录为出站 ERROR。调用方在流上下文中抛出的非 HTTP 业务异常也不会被误报为出站流失败。完整事件列表见[日志](logging.md)。

## 8. 生命周期与依赖边界

`HttpClientManager` 延迟到首次请求才创建两个 HTTPX2 client。应用关闭时，`ApplicationContainer` 逆序执行异步关闭 callback；未初始化的 HTTP 资源不会为了关闭而创建。Manager 一旦开始关闭便拒绝后续 `get/request/stream`，新的运行周期必须构建新容器。

HTTP/Console 入口可以从容器选择客户端。业务 application service 不应持有整个 `ApplicationContainer`；当上下文需要访问上游时，应在该上下文 application 层定义符合业务语言的窄端口，由 infrastructure 适配器使用公共 HTTP 客户端实现，再由 composition 注入。

HTTPX2 在 `pyproject.toml` 中保留可升级的依赖范围，其传递依赖 httpcore2 只在 `uv.lock` 中记录当前经过验证的精确版本。驱动只使用 HTTPX2 公开接口管理请求、流和连接关闭，不依赖具体版本的私有连接池结构。

升级时执行 `uv lock --upgrade-package httpx2 --upgrade-package httpcore2`，然后运行 `tests/outbound_http/test_http11_cancellation.py`、全部出站 HTTP 测试、类型检查和全量回归。取消测试验证流式与缓冲请求被取消后，单连接池仍可继续服务后续请求；不能只更新锁文件而跳过这条行为回归。
