# 缓存

缓存基础设施把 Redis、Memcached 和进程内 Memory 统一成最小异步字节级 KV 契约。统一的是业务需要的交集：`get`、`set`、`delete`、`exists`；脚手架没有把具体驱动的全部能力伪装成通用接口。

## 1. 最小配置与使用

本地开发配置：

```dotenv
CACHE_DEFAULT=local
CACHE_NAMESPACE=fast-api-scaff
CACHE_DEFAULT_TTL=300
CACHE_CONNECTIONS__LOCAL__DRIVER=memory
CACHE_CONNECTIONS__LOCAL__KEY_PREFIX=local
```

通过应用公共入口使用：

```python
from app.bootstrap.container import ApplicationContainer
from app.infrastructure.cache.codecs.json import JsonCacheCodec


async def example(container: ApplicationContainer) -> None:
    cache = await container.caches.get("local")
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
  → Codec（业务值 ↔ bytes）
```

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

250 字节采用最严格后端约束，保证同一业务 key 可以在 Redis、Memcached 和 Memory 间迁移。中文字符的 UTF-8 长度通常大于字符数，检查的是字节数。

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

适合共享缓存、分布式部署和需要成熟运维能力的场景。当前公共接口只使用 Redis String，不提供 Hash/List/Set/ZSet、Lua、Pub/Sub 或分布式锁。

不要从 `CacheManager` 向业务泄露 `redis.asyncio.Redis`。若业务确实需要集合或原子脚本，应为那项能力定义独立协议和专用 Redis 适配器；不要不断扩大通用 `CacheClient`，迫使 Memcached/Memory 提供虚假实现。

### Memcached

适合简单共享 KV。要注意 250 字节 key、30 天 TTL 解释、值大小和服务端配置。`exists` 通过 `get` 实现，会读取值；它不是独立元数据操作。

### Memory

适合单进程开发和测试。它：

- 不持久化，重启即丢失；
- 不跨 worker/进程共享；
- 以进程时钟判断过期；
- 没有容量淘汰策略；
- 不能模拟真实网络故障、连接池或 Redis/Memcached 全部语义。

不要在多 worker 生产部署中用 Memory 保存会影响正确性的状态，例如 session、验证码、限流计数或分布式幂等记录。

## 8. 延迟连接与健康

`CacheManager` 构造时会校验所有连接配置和 key 前缀，但不立刻连接远端。首次 `get(name)` 创建资源；真正网络错误通常在创建连接、`ping` 或读写时暴露。

检查指定连接：

```python
from app.bootstrap.container import ApplicationContainer


async def check_cache(container: ApplicationContainer) -> bool:
    return await container.caches.ping("session")
```

`connection_names` 只是配置名称，`is_initialized` 只是资源创建状态，只有实际 `ping`/读写能说明后端当前可达。

应用关闭会逆序关闭已初始化缓存资源。多个关闭错误会聚合，不会只保留最后一个。Manager 进入关闭后是终态：不会创建未初始化资源，也不允许再次获取客户端；新的宿主生命周期必须构建新的容器和 Manager。

## 9. 错误分类与降级

| 异常 | 含义 |
| --- | --- |
| `CacheConfigurationError` | 名称、driver、字段、namespace/prefix 等配置错误 |
| `CacheConnectionError` | 后端无法连接或 ping 失败 |
| `CacheOperationError` | get/set/delete/exists 失败或返回不符合契约 |
| `CacheKeyError` | 业务 key 不符合跨驱动规则 |

脚手架不会在 Redis 失败后自动切换到 Memory，也不会吞掉错误当作 cache miss。透明回退会造成危险歧义：调用方无法区分“数据不存在”和“缓存服务故障”，不同实例还可能得到彼此隔离的本地状态。

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

- HTTP/Console/Scheduler 等宿主和组合根可以使用容器；
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
| 多 worker 数据不一致 | 是否错误使用 Memory |
| 把 dict 传给 set 报错 | 显式使用 JsonCacheCodec |
| Redis 挂了却没有自动回退 | 这是契约；在业务适配器定义可观测降级策略 |
| 缓存读到旧结构 | codec/schema 版本与旧 TTL 数据 |

更完整的联合排查见[故障排查](troubleshooting.md)。
