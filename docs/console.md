# Console 命令

Console 是与 HTTP 并列的一次性应用宿主。它通过同一个 `ApplicationRuntime` 和 `ApplicationContainer` 调用应用服务，因此业务规则、事务边界和数据库映射与 HTTP 保持一致。

## 1. 查看帮助和版本

```bash
uv run python -m app.interfaces.console --help
uv run python -m app.interfaces.console --version
uv run python -m app.interfaces.console app --help
uv run python -m app.interfaces.console users --help
```

不带命令时显示帮助。当前命令：

| 命令 | 是否构建容器 | 用途 |
| --- | --- | --- |
| `app info` | 否 | 显示应用、时区和已声明连接名 |
| `users create` | 是 | 通过用户应用服务创建用户 |
| `users list` | 是 | 通过用户应用服务分页查询用户 |

## 2. 应用信息

```bash
uv run python -m app.interfaces.console app info
```

输出是单行 JSON，包含：

- `name`、`version`、`environment`、`debug`；
- 当前进程本地时区名称和 offset；
- `.env` 中声明的数据库连接名；
- `.env` 中声明的缓存连接名。

它只读取配置，不构建应用容器，也不会验证数据库、缓存网络或迁移状态。看到连接名只能证明配置字典中存在该名称。

## 3. 用户命令

创建用户：

```bash
uv run python -m app.interfaces.console users create \
  --username alice \
  --email alice@example.com \
  --display-name Alice
```

分页查询：

```bash
uv run python -m app.interfaces.console users list --page 1 --limit 20
```

约束与 HTTP 一致：`page >= 1`，`1 <= limit <= 100`；默认值分别为 1 和 20。分页结果包含 `items`、`total`、`page` 和 `limit`。用户资料还会经过领域校验。用户上下文固定使用 `main` 数据库连接，运行前必须完成 Alembic 迁移。

## 4. 输出协议

可供脚本消费的结果写到 stdout：

```bash
result="$(uv run python -m app.interfaces.console users list)"
```

日志与错误写到 stderr。这样管道和命令替换不会混入结构化日志：

```bash
uv run python -m app.interfaces.console users list \
  1>users.json \
  2>users.log
```

结果由 `ConsolePresenter` 序列化为 JSON：dataclass 转对象，UUID 转字符串，枚举转值，日期时间使用 ISO 8601。当前时间是本地无时区值，所以 ISO 字符串通常不带 offset。

不要在命令处理器里用 `print()` 随意输出调试信息，否则会破坏 stdout 的机器可读契约。诊断信息应走日志或 stderr。

## 5. 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 命令成功 |
| `1` | 可预期的业务、配置、数据库、缓存或日志运行失败 |
| `2` | Typer 参数解析/用法错误 |

自动化脚本应同时检查退出码和 stdout，不要通过匹配中文错误文本判断成功。业务错误文本可能调整，退出码才是命令行协议。

## 6. 生命周期

依赖容器的命令按以下顺序执行：

```text
读取并缓存 Settings
  → 配置 Console 日志
  → 构建 ApplicationRuntime
  → 构建并启动 ApplicationContainer
  → 执行异步 operation
  → 逆序关闭已初始化资源
  → 输出结果
```

命令失败时，上下文管理器仍会尝试关闭容器。关闭阶段多个资源同时失败时可能形成 `ExceptionGroup`，不应为了隐藏关闭错误而直接终止进程。

`app info` 是特例：它只需要配置快照，所以直接调用 settings loader，避免无意义地构建缓存、数据库和用户上下文。

## 7. 新增命令

命令自动扫描 `app.interfaces.console.commands` 包。一个典型命令应继承 `ConsoleCommand`：

```python
from app.interfaces.console.command import ConsoleCommand


class ExampleConsoleCommand(ConsoleCommand):
    group = "example"
    group_help = "示例命令。"
    name = "run"
    help = "执行示例用例。"

    def handle(self) -> None:
        self._console.presenter.text("ok")
```

需要应用依赖时，把异步业务操作写成接收 `ConsoleContext` 的函数，再通过 `self._console.run(operation)` 执行。命令应调用 `context.container.<context>.service`，不应直接创建 Repository、Session 或具体缓存驱动。

自动发现规则：

- 模块必须位于 `app.interfaces.console.commands` 下；
- 类必须是定义在该模块中的非抽象 `ConsoleCommand` 子类；
- 按 `(group, name)` 排序注册；
- 相同 group 的 `group_help` 必须一致；
- 重复 `(group, name)` 会在创建 Console 时失败。

## 8. 导入副作用

命令模块会被自动 import，因此模块顶层必须保持轻量、确定且无外部副作用。禁止在 import 时：

- 访问数据库、缓存或网络；
- 读取业务数据；
- 创建事件循环或后台任务；
- 修改文件、数据库或远端状态；
- 根据运行时条件动态注册不同命令；
- 执行实际命令逻辑。

参数声明、类定义和纯常量可以放在模块顶层；真实动作只能发生在 `handle()` 或它调用的 operation 中。

## 9. 错误处理边界

- Typer 负责参数格式和必填项错误；
- command 负责把该用例的已知领域/应用错误输出为可读错误并返回 1；
- Console 根入口统一处理配置、日志、数据库和缓存基础设施错误；
- 未预期的编程错误不应被全部吞掉，否则会掩盖缺陷。

与 HTTP 相同，不要把任意数据库 `IntegrityError` 都显示为“用户名已存在”。只有基础设施层明确识别具体约束后，应用层才能输出稳定业务错误。

## 10. 测试建议

- 纯信息函数可直接传入 Settings 测试；
- operation 使用替身 `ConsoleContext` 或测试容器验证应用调用；
- 使用 Typer `CliRunner` 验证参数、stdout、stderr 和退出码；
- 至少覆盖命令重复、group help 冲突和自动发现；
- 集成测试使用临时 SQLite，并先运行/创建对应 schema；
- 验证失败命令也会关闭已初始化资源。

## 11. 常见误区

- `app info` 不验证连接可达性。
- 修改 `.env` 后，已经运行的 Python 进程仍持有缓存配置；重新执行命令即可获得新进程。
- stdout 是结果协议，不应混入日志。
- Console 不应复制 HTTP controller 逻辑，而应直接复用 application service。
- 一次性 Console 不适合承载常驻调度循环；未来 Scheduler 应作为独立宿主复用 runtime，而不是塞进某个命令后无限运行。

架构关系见[架构说明](architecture.md)，数据库命令故障见[故障排查](troubleshooting.md)。
