# 缓存

缓存基础设施把 Redis 和 Memcached 统一成最小异步字节级 KV 契约。统一的是业务需要的交集：`get`、`set`、`delete`、`exists`；脚手架没有把具体驱动的全部能力伪装成通用接口。

## 1. 最小配置与使用

本地开发配置：

```dotenv
CACHE_DEFAULT=session
CACHE_NAMESPACE=fast-api-scaff
CACHE_DEFAULT_TTL=300
CACHE_CONNECTIONS__SESSION__DRIVER=redis
CACHE_CONNECTIONS__SESSION__HOST=127.0.0.1
CACHE_CONNECTIONS__SESSION__PORT=6379
CACHE_CONNECTIONS__SESSION__DATABASE=0
CACHE_CONNECTIONS__SESSION__KEY_PREFIX=session
```

通过应用公共入口使用：

```python
from app.runtime.container import ApplicationContainer
from app.infrastructure.cache.codecs.json import JsonCacheCodec


async def example(container: ApplicationContainer) -> None:
    cache = await container.caches.get("session")
    await cache.set("users:summary", JsonCacheCodec.encode({"total": 3}))

    raw = await cache.get("users:summary")
    value = None if raw is None else JsonCacheCodec.decode(raw)
    print(value)
```

这是宿主/集成层示例。具体限界上下文若把缓存作为用例的一部分，应先在 application/domain 边界定义业务语义明确的窄协议，例如 `UserProfileCache`，再由基础设施适配器内部使用 `CacheClient`。不要把 `CacheManager` 注入领域对象。

## 2. 组件分层

```text
ApplicationContainer
  → CacheManager（命名资源、默认连接、生命周期）
  → Provider（解析 driver 配置并创建资源）
  → Connection（客户端/连接池与 ping/close）
  → Storage（后端字节级 KV 操作）
  → ManagedCacheClient（统一 key 与 TTL）
      ↳ ManagedRedisCacheClient（Redis TTL 与受控脚本执行）
  → Codec（业务值 ↔ bytes）
```

缓存契约按职责拆分：`app.infrastructure.cache.contracts.storage` 定义通用 `KeyValueStorage`；`contracts.redis` 定义 Redis TTL 与组合协议；`contracts.script` 定义 `RedisScriptArgument` 和 `RedisScriptExecutor`。脚本具体实现位于 `storages/redis/script.py`，与契约分开；调用方从符号实际定义的模块导入。

Redis 使用 `RedisStorage` 聚合数据类型适配器，当前 `strings` 实现通用 KV 契约。各数据类型 Storage 继承 `BaseRedisStorage`，统一保存从 Connection 借用的客户端引用；基类不拥有客户端，不负责连接建立、健康检查或关闭，这些生命周期职责仍由 Connection 承担。

`RedisStorage.scripts` 使用与 String 相同的借用连接，通过独立 `RedisScriptExecutor` 执行脚本并转换驱动异常；缓存层不加载场景脚本，不解释计数、配额或锁定结果。

Lua 资源由使用它们的组件持有：登录脚本位于 `app/contexts/user/infrastructure/security/scripts/`，固定窗口脚本位于 `app/infrastructure/rate_limit/scripts/`。所属适配器按模块位置在首次导入时读取资源，不依赖启动目录。资源目录不是 Python 包。源码发布必须包含这些 Lua 文件；当前 Dockerfile 整体复制项目且 `.dockerignore` 未排除 Lua 资源。若以后增加 wheel 发布，需要将资源纳入打包并验证。

后续需要 ZSet 或 List 时，应分别增加继承同一基类的 `RedisSortedSetStorage`、`RedisListStorage`，由 `RedisStorage` 使用同一个客户端组合。Redis 专属能力不进入 Redis/Memcached 共用的 `CacheClient`。当前 `CacheManager.get_redis(name)` 是显式能力入口，返回 `ManagedRedisCacheClient`；选择 Memcached 或其他连接时会在创建资源前返回清楚的配置错误。后续类型应沿用这一入口和聚合方式增加专属客户端能力，不给 Memcached 增加伪实现。

职责隔离的价值：

- Manager 不暴露 Redis/Memcached 具体客户端；
- Storage 吸收驱动调用差异；
- Managed client 保证所有驱动使用相同 key/TTL 规则；
- Codec 显式决定序列化；
- 业务适配器表达“缓存什么”，而不是“用哪个驱动”。

## 3. CacheClient 契约

```python
class CacheClient(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, *, ttl=DEFAULT_EXPIRATION) -> None: ...
    async def delete(self, key: str) -> bool: ...
    async def exists(self, key: str) -> bool: ...
```

`set` 只接受 `bytes`，传字符串、dict 或 Pydantic model 会抛出 `TypeError`。这是刻意设计：隐式序列化容易产生不兼容数据，显式 codec 才能让 schema 演进可见。

`delete/exists` 的布尔值表示目标 key 当时是否存在或删除是否生效，不应当作强一致业务事实。缓存随时可能过期或被其他进程修改。

Redis 专属客户端在公共 KV 方法之外提供 `expire`、`ttl` 和 `execute_script`。脚本入口只供基础设施适配器使用，不进入 Domain/Application，也不暴露原生 Redis 客户端。

```python
async def execute_script(
    self,
    script: str,
    *,
    keys: tuple[str, ...],
    args: tuple[str | bytes | int, ...] = (),
) -> object: ...
```

脚本必须为非空字符串，`keys` 为非空元组，所有 key 都在调用前经 namespace/prefix 规则处理；`args` 为字符串、字节或整数元组，不接受布尔值。默认缓存 TTL 不参与脚本执行。返回值保持驱动原始形态，由场景适配器校验；驱动错误统一转换为 `CacheOperationError`，取消继续传播。

脚本只能来自随代码发布的受信任资源，不能来自 HTTP/Console 输入。脚本作者必须通过 `KEYS` 访问所有键，不从 `ARGV` 或文本拼接键。接口不会分析 Lua，也不是权限沙箱；多 key 脚本的 Redis Cluster 同槽约束仍由调用方负责，当前接口不增加 Cluster 支持。

旧的 `increment`、`delete_below`、`acquire_window` 已从公共客户端移除。登录固定窗口、锁定阈值和条件清理由用户上下文适配器负责；请求配额由独立限流组件负责。新增场景应在所属模块实现策略和结果校验，复用脚本入口，不继续向公共缓存追加场景方法。

## 4. Key 规则

最终 key：

```text
namespace:key_prefix:business_key
```

例如：

```dotenv
CACHE_NAMESPACE=my-service
CACHE_CONNECTIONS__SESSION__KEY_PREFIX=session
```

业务 key `user:42` 最终得到 `my-service:session:user:42`。

跨驱动约束：

- namespace 在配置连接时必须非空；
- namespace/prefix 不能包含空白或控制字符；
- namespace/prefix 不能以 `:` 开头或结尾；
- 业务 key 不能为空，不能包含空白或控制字符；
- 最终 key 的 UTF-8 长度不能超过 250 字节。

250 字节采用最严格后端约束，保证同一业务 key 可以在 Redis 和 Memcached 间迁移。中文字符的 UTF-8 长度通常大于字符数，检查的是字节数。

建议格式：

```text
resource:{id}:representation:v1
```

不要把密码、token、邮箱等敏感值直接拼进 key；它们可能出现在运维界面和日志。对长或敏感维度可做稳定哈希，但仍要保留可识别的业务前缀。

## 5. TTL 语义

`set` 支持三种方式：

```python
from app.infrastructure.cache.contracts.client import NO_EXPIRATION

await cache.set("a", b"value")                 # 使用 CACHE_DEFAULT_TTL
await cache.set("b", b"value", ttl=60)         # 60 秒
await cache.set("c", b"value", ttl=NO_EXPIRATION)  # 永不过期
```

规则：

- 默认 TTL 来自 `CACHE_DEFAULT_TTL`，默认 300 秒；
- 显式 TTL 必须是正整数，`bool` 不被视为整数；
- `NO_EXPIRATION` 映射为后端不设过期；
- 代码构造 `CacheSettings(default_ttl=None)` 时默认写入不过期；`.env` 的 `CACHE_DEFAULT_TTL` 只能写正整数；
- 过期并不保证后端在精确时刻主动删除，但之后读取应视为不存在。

Memcached 把大于 30 天的 expiry 解释为 Unix 时间戳。适配器会将超过 30 天的相对 TTL 转换成当前时间 + TTL，避免写入后立即过期。系统时钟异常仍会影响这一转换。

## 6. Codec

内置 codec：

| Codec | 输入 | 输出/注意事项 |
| --- | --- | --- |
| `BytesCacheCodec` | `bytes` | 原样返回 |
| `TextCacheCodec` | `str` | UTF-8 编解码 |
| `JsonCacheCodec` | JSON 可序列化对象 | 紧凑 UTF-8 JSON；decode 返回普通 Python 对象 |

示例：

```python
from app.infrastructure.cache.codecs.text import TextCacheCodec

await cache.set("greeting", TextCacheCodec.encode("你好"), ttl=60)
raw = await cache.get("greeting")
greeting = None if raw is None else TextCacheCodec.decode(raw)
```

复杂对象不要直接依赖 `default=str` 之类的宽松转换。推荐先转换为版本化 DTO/dict，并在 key 或 payload 中保存 schema 版本。改变 JSON 结构时需要考虑旧缓存仍在 TTL 内。

## 7. 后端选择

### Redis

适合共享缓存、分布式部署和需要原子脚本操作的场景。当前提供 String KV、TTL 与受控脚本执行；未提供 Hash/List/Set/ZSet、Pub/Sub 或分布式锁等封装。

登录策略见[认证](authentication.md)，固定窗口的准入、重试秒数和故障策略见[HTTP 请求限流](http.md#13-http-请求限流)。两者借用同一缓存资源体系，策略与脚本分别归属其自身模块，不由缓存层决定。

### Memcached

适合简单共享 KV。要注意 250 字节 key、30 天 TTL 解释、值大小和服务端配置。`exists` 通过 `get` 实现，会读取值；它不是独立元数据操作。

## 8. 延迟连接与健康

`CacheManager` 构造时会校验所有连接配置和 key 前缀，但不立刻连接远端。`require_redis(name)` 只校验连接是否存在且 driver 为 Redis；首次 `get(name)` 或 `get_redis(name)` 才创建资源。真正网络错误通常在 `ping` 或读写时暴露。

检查指定连接：

```python
from app.runtime.container import ApplicationContainer


async def check_cache(container: ApplicationContainer) -> bool:
    return await container.caches.ping("session")
```

`connection_names` 只是配置名称，`is_initialized` 只是资源创建状态，只有实际 `ping`/读写能说明后端当前可达。

应用关闭会逆序关闭已初始化缓存资源。多个关闭错误会聚合，不会只保留最后一个。Manager 在第一次等待前统一禁止全部连接的新获取，再逆序释放资源。关闭前已经开始的初始化可以完成，但结果只交给清理流程，不再返回调用方；等待中的获取也会被拒绝。关闭失败后仍保持禁止获取，后续 `aclose()` 可以重试未完成的清理。宿主应先停止使用已经借出的客户端，再关闭 Manager。新的宿主生命周期必须构建新的容器和 Manager。

## 9. 错误分类与降级

| 异常 | 含义 |
| --- | --- |
| `CacheConfigurationError` | 名称、driver、字段、namespace/prefix 等配置错误 |
| `CacheConnectionError` | 后端无法连接或 ping 失败 |
| `CacheOperationError` | get/set/delete/exists 或 Redis 原子计数/TTL 操作失败，或返回不符合契约 |
| `CacheKeyError` | 业务 key 不符合跨驱动规则 |

脚手架不会在一个缓存连接失败后自动切换到其他连接或进程内临时存储，也不会吞掉错误当作 cache miss。透明回退会造成危险歧义：调用方无法区分“数据不存在”和“缓存服务故障”，不同实例还可能访问不一致的数据。

是否降级属于业务策略：

- 纯性能缓存可在业务适配器中记录故障并回源；
- session、幂等、锁、限流等正确性缓存通常应失败关闭；
- 回源要防止缓存击穿和数据库雪崩；
- 降级必须可观测，不能静默。

## 10. Cache-Aside 示例边界

推荐在上下文基础设施适配器中实现：

```text
Application Service
  → UserProfileCache 协议
  → Cache-backed adapter
      → CacheClient
      → User DTO codec
```

读取流程可以是 cache → miss → repository → cache set；写流程通常是数据库 commit 后删除或更新缓存。具体顺序取决于容忍陈旧数据的程度。

不要在聚合方法中读写缓存。聚合应根据已提供的数据执行确定性规则，外部 I/O 由应用服务/适配器协调。

## 11. 扩展新驱动

1. 定义严格的 Pydantic 配置模型，禁止额外字段并隐藏秘密；
2. 实现 connection 生命周期和 `ping/aclose`；
3. 实现字节级 `KeyValueStorage`，把驱动异常转换成稳定缓存异常；
4. 构建 Provider factory；
5. 注册到 `CacheProviderRegistry`；
6. 复用 `ManagedCacheClient`，不要跳过 key/TTL 规则；
7. 添加契约测试，确保 get/set/delete/exists 与 TTL 在各驱动一致；
8. 更新 `sample.env`、[配置参考](configuration.md)和本章。

如果新后端无法诚实满足字节级 KV 契约，应建立新的能力接口，而不是硬塞进现有抽象。

## 12. “容器和缓存抽象会诱导边界穿透”的含义

`ApplicationContainer` 和 `CacheManager` 很方便，但如果任何业务类都直接接收它们，就能随意访问所有数据库、缓存和其他上下文服务。结果是依赖关系隐藏在运行时属性访问里，限界上下文失去所有权，测试也只能构造一个巨型容器。

合理边界：

- HTTP/Console/Worker/Scheduler 等宿主和组合根可以使用容器；
- 基础设施适配器可以使用指定的 `CacheClient`；
- application service 依赖业务命名的窄协议；
- domain 不依赖容器、Manager 或具体驱动。

容器是装配工具，不是 Service Locator；缓存抽象是基础设施能力，不是允许跨上下文共享任意 key 的全局数据总线。

## 13. 排查清单

| 症状 | 检查项 |
| --- | --- |
| 启动时报缓存配置不合法 | 所有连接都会启动校验；检查未使用连接、JSON、namespace/prefix |
| Redis 配置正确但首次请求失败 | 网络、DNS、TLS、认证、数据库编号和超时 |
| key 报超过 250 字节 | 检查最终 namespace + prefix + key 的 UTF-8 长度 |
| Memcached 长 TTL 立即过期 | 系统时钟和 30 天转换 |
| 多 worker 数据不一致 | 各实例是否连接同一后端、database 和 namespace |
| 把 dict 传给 set 报错 | 显式使用 JsonCacheCodec |
| Redis 挂了却没有自动回退 | 这是契约；在业务适配器定义可观测降级策略 |
| 缓存读到旧结构 | codec/schema 版本与旧 TTL 数据 |

更完整的联合排查见[故障排查](troubleshooting.md)。
