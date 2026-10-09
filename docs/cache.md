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
      ↳ ManagedRedisCacheClient（Redis 数据类型、TTL 与受控脚本执行）
  → Codec（业务值 ↔ bytes）
```

缓存契约按职责拆分：`app.infrastructure.cache.contracts.storage` 定义通用 `KeyValueStorage`；`contracts.redis` 定义 Redis 数据类型契约与 `RedisStorageProtocol` 组合协议；`contracts.script` 定义 `RedisScriptArgument` 和 `RedisScriptExecutor`。脚本具体实现位于 `storages/redis/script.py`，与契约分开；调用方从符号实际定义的模块导入。

Redis 使用 `RedisStorage` 聚合 `keys`、`strings`、`hashes`、`sets`、`sorted_sets` 和 `scripts`。String 负责字节读写及 NX 写入；删除、存在性和 TTL 属于与值类型无关的 Key 适配器。各数据类型 Storage 继承 `BaseRedisStorage`，统一保存从 Connection 借用的客户端引用；基类不拥有客户端，不负责连接建立、健康检查或关闭，这些生命周期职责仍由 Connection 承担。

Redis 聚合契约从 `RedisAtomicStorage` 更名为 `RedisStorageProtocol`。自定义 Redis Provider 的 Storage 需要实现上述入口及通用 KV 方法；TTL 入口已从 `strings` 移至 `keys`。公共 `ManagedRedisCacheClient.expire/ttl` 的调用方式保持一致。

`RedisStorage.scripts` 使用与 String 相同的借用连接，通过独立 `RedisScriptExecutor` 执行脚本并转换驱动异常；缓存层不加载场景脚本，不解释计数、配额或锁定结果。

Lua 资源由使用它们的组件持有：登录脚本位于 `app/contexts/user/infrastructure/security/scripts/`，固定窗口脚本位于 `app/infrastructure/rate_limit/scripts/`。所属适配器按模块位置在首次导入时读取资源，不依赖启动目录。资源目录不是 Python 包。项目通过 `uv_build` 将顶层 `app` 模块及其中的 Lua 资源写入 wheel；`tests/test_distribution.py` 会构建并安装 wheel，再从安装目录导入登录限制和 HTTP 限流适配器，验证三个脚本均可加载。Dockerfile 仍通过整体复制项目包含这些资源。

Redis 专属能力不进入 Redis/Memcached 共用的 `CacheClient`。`CacheManager.get_redis(name)` 是显式能力入口，返回 `ManagedRedisCacheClient`；选择 Memcached 或其他连接时会在创建资源前返回清楚的配置错误。扩展新的数据类型时应沿用这一入口，由 `RedisStorage` 使用同一个客户端组合，不给 Memcached 增加伪实现。

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

Redis 专属客户端在公共 KV 方法之外提供以下操作；所有 key 经过同一命名空间、连接前缀和有效性校验，Hash 字段与集合成员不添加 key 前缀。

| 方法 | 语义 |
| --- | --- |
| `expire(key, ttl=...)` / `ttl(key)` | 更新正整数秒级 TTL，读取 TTL 时保留 `-1`（不过期）和 `-2`（不存在） |
| `set_if_absent(key, value, ttl_ms=...)` | 通过 NX 条件写入字节值，TTL 为显式正整数毫秒；成功新增返回 `True`，已存在返回 `False` |
| `hash_get_all(key)` | 返回 `dict[bytes, bytes]`，缺失时返回空字典 |
| `hash_set(key, mapping)` | 写入非空字段字典，字段名为非空字符串、值为字节；返回新增字段数，保留未指定字段 |
| `set_add(key, member)` | 添加一个字节成员，新增返回 `True`，已存在返回 `False` |
| `sorted_set_add(key, member, score=..., nx=False)` | 添加或更新字节成员，返回是否新增；`nx=True` 时保留已有分数 |
| `sorted_set_remove(key, member)` | 移除字节成员，返回是否存在 |
| `sorted_set_range_by_score(key, minimum=..., maximum=..., count=..., offset=0)` | 读取闭区间内的成员，按分数升序和同分成员字节顺序返回 `tuple[bytes, ...]`，不移除成员 |
| `execute_script(script, keys=..., args=...)` | 借用连接执行受信任脚本，由调用适配器解释结果 |

分数和范围边界拒绝布尔值、非数字和 NaN；范围边界可使用正负无穷，`offset` 必须为非负整数，`count` 必须为正整数。Hash、Set 和 Sorted Set 操作不应用默认 TTL，也不自动刷新 TTL；需要过期时显式调用 `expire`。`set_if_absent` 不应用默认秒级 TTL，也不提供锁续租或释放策略。驱动错误与非法返回值转换为 `CacheOperationError`，任务取消继续传播。

宿主或基础设施适配器可通过公共入口使用：

```python
from app.runtime.container import ApplicationContainer


async def use_redis_types(container: ApplicationContainer) -> tuple[bytes, ...]:
    cache = await container.caches.get_redis("session")
    await cache.hash_set("profile", {"name": "alice".encode("utf-8")})
    await cache.set_add("members", b"alice")
    await cache.sorted_set_add("due", b"alice", score=100, nx=True)
    return await cache.sorted_set_range_by_score("due", minimum=0, maximum=100, count=20)
```

Domain/Application 使用所属上下文定义的窄协议，不直接接收 Redis 专属客户端。脚本入口只供基础设施适配器使用，不暴露原生 Redis 客户端。

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

适合共享缓存、分布式部署和需要原子脚本操作的场景。当前提供 String KV、NX 毫秒 TTL、Hash 读写、Set 添加、Sorted Set 写入/删除/分数查询及受控脚本执行。各数据类型仅提供上表列出的操作，没有封装驱动的全部命令；当前未提供 List、Pub/Sub 或完整分布式锁策略。

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
| `CacheOperationError` | KV、Redis 数据类型、TTL 或脚本操作失败，或返回不符合契约 |
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
