# 项目代码规则

## 协作确认规则

在修改代码、配置、测试、文档、依赖或项目结构之前，AI 编码代理必须先向用户说明：

1. 拟修改的内容和涉及文件；
2. 修改原因及预期结果；
3. 可能产生的影响；
4. 计划执行的验证方式。

说明完成后，必须等待用户明确确认，未经确认不得开始写入。

用户的确认仅对已说明的修改范围有效。实施过程中如果需要新增文件、扩大范围、调整方案或产生未提前说明的影响，必须暂停操作，重新说明并再次获得确认。

未经确认，禁止执行以下操作：

- 新增、编辑、移动、重命名或删除文件；
- 自动格式化、代码生成或批量重构；
- 增删依赖、更新锁文件或执行配置迁移；
- 更新测试快照或其他基准文件；
- 执行会改变工作区、暂存区、提交历史、分支或远端状态的 Git 操作。

下列操作可以直接执行：

- 阅读代码、配置和文档；
- 搜索文件、符号和调用关系；
- 查看 Git 状态、差异和历史；
- 运行测试、Lint、类型检查等验证命令；这些命令生成的可安全删除且不影响程序行为的临时缓存，例如 `.pytest_cache`、`__pycache__` 和 `.ruff_cache`，不视为项目修改，无需单独确认；
- 分析问题并提供修改方案。

如果验证命令会更新受版本控制文件、测试快照、锁文件、生成代码、业务数据或外部状态，仍必须先获得用户确认。

除上述允许的临时缓存外，一旦操作可能写入或改变项目文件、改变项目状态或影响外部系统，必须先获得用户确认。

## Python 语法

- 项目目标版本为 Python 3.14+，新代码应优先使用该版本支持的现代语法。
- 可空类型使用 `T | None`，不使用 `Optional[T]`。
- 容器类型使用内置泛型，例如 `list[str]`、`dict[str, object]`、`tuple[int, ...]`，不使用 `List`、`Dict`、`Tuple` 等旧式写法。
- 类型别名使用 `type` 语句，泛型类和泛型函数优先使用 PEP 695 语法。
- `Callable`、`Awaitable`、`Iterator`、`AsyncIterator` 等运行时协议优先从 `collections.abc` 导入。
- 只有在第三方库的类型声明或兼容性明确要求时，才保留旧式 `typing` 写法，并在局部范围内使用。

推荐：

```python
from collections.abc import AsyncIterator, Callable

type Handler[T] = Callable[[T], None]


async def stream() -> AsyncIterator[bytes]:
    yield b"data"
```

避免：

```python
from typing import AsyncIterator, Callable, Dict, Optional


def find() -> Optional[Dict[str, str]]:
    ...
```

## Python 包初始化文件

- 新建 Python 包目录时应创建 `__init__.py`。
- 所有 `__init__.py` 必须是完全空文件，不能包含注释、文档字符串或空白说明文字。
- 禁止在 `__init__.py` 中导入或重新导出符号。
- 禁止在 `__init__.py` 中声明 `__all__`、常量、函数或类，也不能执行注册等初始化逻辑。
- 包初始化之外的逻辑应放在含义明确的独立模块中。

## 导入

- 使用绝对且显式的模块路径，从符号实际定义的模块导入。
- 禁止依赖 `__init__.py` 进行包级聚合导出。
- 禁止使用通配符导入，例如 `from module import *`。
- 导入顺序依次为标准库、第三方库、项目内部模块，各组之间保留一个空行，并交由 Ruff 统一排序。

推荐：

```python
from app.bootstrap.container import ApplicationContainer
from app.config.settings import load_settings
```

避免：

```python
from app.bootstrap import ApplicationContainer
from app.config import *
```

## 函数长度

- 单个函数或方法建议不超过 80 行，统计时包含函数体内的注释和空行，不包含装饰器。
- 超过 80 行时，应优先检查函数是否承担了多个职责、存在重复步骤或嵌套过深。
- 拆分出的私有函数应有清晰职责和名称，不能只是为了满足行数而机械切割连续代码。
- 优先使用提前返回、提取独立步骤和减少嵌套的方式改善可读性。
- 80 行是代码审查提示线，不是必须牺牲完整性才能满足的硬性限制；确有必要超过时，应保证职责仍然单一且流程清晰。
