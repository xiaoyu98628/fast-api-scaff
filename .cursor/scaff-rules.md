# demo2 项目规则索引

与 **demo1** 的工程化约定一致，但目录映射为 **demo2 扁平结构**（无 `application/`、`domain/`、`common/`、`interfaces/`、`infrastructure/db/` 分包）。

详细规则见 **`.cursor/rules/`** 下各 `.mdc` 文件：

| 文件 | 内容 |
|------|------|
| `fastapi-demo2-architecture.mdc` | 目录树、调用链、Session、中间件与异常出口 |
| `fastapi-demo2-api-router.mdc` | 路由聚合、REST、`index`/`store`/`show` 等命名 |
| `fastapi-demo2-errors.mdc` | 十位错误码、`BizException`/`SystemException`、`core/errors` |
| `fastapi-demo2-enums.mdc` | `app/enums` 放置约定与 ORM/Pydantic 用法 |
| `fastapi-demo2-python.mdc` | import、`__init__.py`、函数长度（匹配 `**/*.py` 时生效） |

协作或 AI 辅助时：**架构与错误码类规则默认始终生效**；Python 风格规则在编辑 `.py` 时按 glob 附加。
