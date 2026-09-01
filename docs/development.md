# 开发与质量

本章给出从修改到交付的完整检查路径。不要把“测试通过”理解成只运行一个 happy path；验证强度应与变更影响的层次、数据和生命周期风险匹配。

## 1. 开发环境

安装生产与开发依赖：

```bash
uv sync --extra dev
```

项目目标 Python 版本为 3.14+。依赖和锁文件应由 uv 管理；不要混用未记录的全局环境，避免“本机能运行、CI 无法复现”。

复制示例配置：

```bash
cp sample.env .env
```

测试通常会构造隔离配置或临时 SQLite，不应依赖开发者真实数据库。任何会改变业务数据或版本控制文件的验证都应先明确目标和影响。

## 2. 常用质量命令

完整测试：

```bash
uv run python -m pytest -q
```

按领域快速反馈：

```bash
uv run python -m pytest -q tests/users
uv run python -m pytest -q tests/http
uv run python -m pytest -q tests/database
uv run python -m pytest -q tests/cache
uv run python -m pytest -q tests/console
uv run python -m pytest -q tests/logging
```

架构边界：

```bash
uv run python -m pytest -q tests/test_architecture.py
```

Lint、格式检查和类型检查：

```bash
uv run ruff check app tests database
uv run ruff format --check app tests database
uv run ty check app tests database
```

文档改动还应执行：

```bash
git diff --check
```

Ruff format 的 `--check` 不修改文件；实际格式化会改变代码，执行前遵守项目确认规则并确保范围明确。

## 3. 测试分层

### Domain

验证聚合和值对象，不连接数据库：

- 合法创建、规范化和默认状态；
- 每个不变量的失败路径；
- 命名行为的状态变化；
- 本地无时区 datetime 规则；
- `rehydrate()` 对持久化脏数据的拒绝；
- 固定 ID/时钟下的确定性。

### Application

用 fake repository/UoW 测试流程：

- 用例调用顺序与 commit；
- not found、预检查冲突；
- 异常时不误提交；
- DTO 不泄露聚合可变状态；
- offset/limit 等用例输入语义。

### Infrastructure

验证真实适配器契约：

- Domain ↔ ORM mapper；
- Repository 查询顺序和排除当前 ID；
- UoW commit/rollback/异常映射；
- Manager 延迟初始化和关闭；
- Provider 配置严格性；
- cache key/TTL/codec 跨驱动一致性；
- 日志字段和敏感参数隐藏。

### Interface

HTTP 测试覆盖 status、统一响应、schema、错误映射、中间件和 OpenAPI；Console 测试覆盖参数、stdout/stderr、退出码、发现和生命周期。

不要让 HTTP 测试成为唯一业务测试，否则 Console 或未来其他宿主复用时无法证明规则独立于 FastAPI。

## 4. 架构约束

架构测试扫描 `app/contexts/*/domain` 与 `application` 的绝对 import：

- Domain 只能依赖当前上下文 Domain 和标准库；
- Application 只能依赖当前上下文 Application/Domain 和标准库；
- 相对导入视为违规；
- 一个上下文不能直接 import 另一个上下文内部层。

这项测试没有覆盖所有设计问题。例如它不能发现 application service 接收 `object` 后在运行时当容器使用，也不能判断 Repository 是否偷偷 commit。因此仍需要构造签名审查、代码审查和行为测试。

## 5. Python 代码约定

- 使用 Python 3.14 现代语法：`T | None`、内置泛型、`type`、PEP 695；
- `Callable`、`AsyncIterator` 等从 `collections.abc` 导入；
- 从符号实际定义模块绝对导入；
- 禁止通配符 import 和包级聚合导出；
- `__init__.py` 必须完全为空；
- 新包目录必须有空 `__init__.py`；
- 顶级包名不得与标准库冲突；
- 单函数 80 行是审查提示线，优先按职责拆分；
- 导入顺序交给 Ruff。

可以检查非空初始化文件：

```bash
find app database -name '__init__.py' -type f -size +0c -print
```

无输出才符合当前规则。

## 6. 新功能的实现顺序

建议顺序：

1. 明确用例、业务边界和不做什么；
2. 列出入口、下游依赖、配置、数据、事务和生命周期影响；
3. 先写 Domain/Application 行为与测试；
4. 实现基础设施适配器和契约测试；
5. 在 composition/container 接线；
6. 增加 HTTP/Console 等入口；
7. 新增或审查 migration；
8. 更新公开配置、`sample.env`、README 和专题文档；
9. 沿完整调用链运行验证。

若功能本质是基础设施宿主，例如常驻 Scheduler，先定义生命周期、信号、并发、任务注册、错误隔离和可观测性，再接业务任务。不要先写一个无限循环，之后再补边界。

## 7. 数据库迁移检查

```bash
uv run alembic -c database/main/alembic.ini current
uv run alembic -c database/main/alembic.ini revision --autogenerate -m "describe change"
uv run alembic -c database/main/alembic.ini upgrade head
uv run alembic -c database/main/alembic.ini downgrade -1
```

生成 revision 会新增项目文件，必须先确认范围。每个 revision 都要人工检查，特别是：

- autogenerate 是否因 model registry 遗漏而漏表；
- 重命名是否被错误识别为 drop + add；
- 非空字段和历史数据回填；
- 约束名和唯一错误映射；
- SQLite batch 与生产方言差异；
- downgrade 的数据损失。

迁移测试至少验证 head 能落地、revision 记录正确、可按预期 downgrade。生产部署应把 schema 变更与应用兼容窗口一起设计。

## 8. 修改公开契约时的同步范围

| 变更 | 至少检查 |
| --- | --- |
| 环境变量 | 配置模型、`sample.env`、README、configuration、测试 |
| HTTP 路由/schema/code | controller、OpenAPI、http 文档、客户端兼容性、测试 |
| Console 命令 | help、stdout/stderr、退出码、console 文档、测试 |
| ORM Model | domain/mapper、registry、migration、方言测试 |
| Cache key/payload | codec 版本、旧数据 TTL、cache 文档、测试 |
| 时间语义 | 所有宿主、domain、DTO、ORM、迁移、日志、文档 |
| Container 生命周期 | HTTP、Console、未来宿主、失败清理、关闭测试 |
| 目录/import | architecture test、README 结构和空 `__init__.py` |

README 只能描述已经实现和验证的功能。规划项可以明确标成“尚未实现”，不能写成当前启动方式。

## 9. 文档维护

文档示例也是公开契约，至少核对：

- 命令可从项目根目录直接运行；
- Alembic 带正确的 `-c database/main/alembic.ini`；
- import 指向定义模块，不依赖 `__init__.py` 重导出；
- 配置键、默认值和校验阶段与代码一致；
- HTTP status、响应体和 204 行为一致；
- 不让业务代码直接使用 Redis/Memcached 驱动；
- 未实现功能没有被包装成现有能力；
- 相对 Markdown 链接存在。

## 10. 提交前检查清单

- 变更范围与原确认一致，没有意外修改依赖、锁文件或配置；
- `git status --short` 中没有不明生成物；
- Domain/Application 依赖方向保持正确；
- 聚合规则没有被 controller/ORM 旁路；
- 写用例的事务与异常映射可解释；
- 多进程、延迟连接、关闭失败和时间语义已经考虑；
- migration 与 model registry 同步；
- `sample.env` 和文档同步公开变化；
- 相关分层测试先通过；
- 全量 pytest、Ruff、格式检查、ty 通过；
- `git diff --check` 通过；
- 最后人工审查 diff，确认没有把样例能力夸大成生产保证。

遇到失败时按[故障排查](troubleshooting.md)缩小范围，而不是通过捕获所有异常、关闭校验或扩大抽象来掩盖问题。
