# FastAPI + DDD（工程化简化版）项目结构规范

## 一、总体设计思想

本项目采用：

* **Clean Architecture（整洁架构）**
* 融合 **DDD（领域驱动设计）思想（轻量版）**

核心原则：

> 分层清晰、职责单一、依赖单向、易扩展

---

## 二、目录结构规范

```text
app/
├── main.py

├── domain/                 # 领域层（核心业务规则，可后期引入）
│
├── application/            # 应用层（用例编排）
│   ├── services/           # 业务服务
│   └── enums/              # 业务相关枚举（默认）

├── interfaces/             # 接口层（对外）
│   ├── api/
│   │   ├── router.py
│   │   └── v1/
│   │       ├── router.py
│   │       └── endpoints/
│   │           └── xxx.py
│   │
│   ├── schemas/            # DTO（请求/响应）
│   └── middleware/         # 中间件（HTTP 层）

├── infrastructure/         # 基础设施层
│   ├── db/
│   │   ├── engine.py
│   │   ├── session.py
│   │   ├── base.py
│   │   └── models/
│   │
│   └── redis/

├── common/                 # 通用模块（跨层）
│   ├── response/           # 统一返回结构
│   ├── enums/              # 仅跨模块通用枚举（错误码等），勿堆业务枚举
│   ├── utils/
│   └── exceptions/

config/                     # 配置层
database/
├── migrations/                 # 数据迁移层（使用 alembic）
```

---

## 三、分层职责说明

### 1. domain（领域层）

* 放核心业务规则（复杂系统才需要）
* 包含：实体、值对象、领域服务

---

### 2. application（应用层）

> 用例编排层（核心）

* 组织业务流程
* 调用 repository / service

示例：

```python
class UserService:
    async def get_user(self, user_id: int):
        ...
```

---

### 3. interfaces（接口层）

#### api

* 定义 HTTP 接口
* 不写业务逻辑

#### schemas

* Pydantic 模型（DTO）
* 请求/响应结构

#### middleware

* HTTP 层逻辑（日志 / trace_id / 解密等）

---

### 4. infrastructure（基础设施层）

> 技术实现层（最底层）

#### db

* 数据库连接与 ORM

#### redis

* 缓存

---

### 5. common（通用层）

> 横切能力

* response（统一返回）
* enums（**仅**跨模块通用：错误码、HTTP 相关等；业务枚举见 `application/enums/` 或 `domain/.../enums.py`）
* utils
* exceptions

---

## 四、调用链规范（必须遵守）

```text
API → Application → Infrastructure
```

禁止：

```text
API → 直接操作 DB ❌
```

---

## 五、数据库模块拆分规范

```text
db/
├── engine.py    # 创建数据库连接
├── session.py   # 会话管理
├── base.py      # ORM 基类
└── models/      # 表结构
```

### 职责：

| 文件         | 作用         |
| ---------- | ---------- |
| engine.py  | 创建数据库连接    |
| session.py | 管理 Session |
| base.py    | ORM 基类     |
| models     | 表结构定义      |

### 原因：

* 避免循环依赖
* 支持多数据库
* 支持测试环境切换
* 方便 Alembic 迁移

---

## 六、Router 设计规范

```text
api/
├── router.py
└── v1/
    ├── router.py
    └── endpoints/
```

### 分层：

1. endpoints：写接口
2. v1/router：聚合模块
3. api/router：聚合版本
4. main.py：挂载

---

### 示例路径：

```text
/api/v1/user/list
```

---

## 七、**init**.py 使用规范

### 必须存在

* 每个目录必须有 `__init__.py`

### 默认策略

* 默认空文件
* 不做导出

---

### 允许使用场景

#### 1. 唯一工具导出

```python
from .codec import DataCodec
```

#### 2. 模块统一出口

```python
from .json import ApiResponse
```

---

### 禁止

```python
from .xxx import *   ❌
```

---

### 原则

> 只在“不会冲突”的情况下做聚合

---

## 八、最佳实践总结

### 1. 分层原则

* 高层不依赖低层实现
* 只依赖抽象

---

### 2. import 规范

推荐：

```python
from app.utils.codec import DataCodec
```

不推荐：

```python
from app.utils import DataCodec  # 除非明确导出
```

---

### 3. 不要过度设计

当前阶段：

* 不强制 DDD 全套
* 先保证分层清晰

---

### 4. 什么时候升级到 DDD

当出现：

* 复杂业务规则
* 多聚合关系
* 多子域协作

---

## 九、一句话核心原则

> 分层不是为了好看，而是为了：
>
> * 解耦
> * 可维护
> * 可扩展
> * 可替换

---

## 十、最终架构心法

```text
接口层：只接请求
应用层：做流程
领域层：管规则
基础设施：做实现
```

---

## 十一、Enum 使用规范（FastAPI + 分层架构）

### 一、核心原则（必须遵守）

> Enum 属于「业务语义」，而不是「数据库实现」

### 二、放置位置规范

#### 1. 业务相关 Enum（默认情况）

放在：

```text
app/application/enums/
```

或（进阶 DDD）：

```text
app/domain/{module}/enums.py
```

#### 示例

```python
# app/application/enums/order_status.py

from enum import Enum

class OrderStatus(int, Enum):
    PENDING = 1
    PAID = 2
    CANCELLED = 3
```

#### 使用

```python
# ORM Model
status = Column(Integer, default=OrderStatus.PENDING.value)

# 业务逻辑
if order.status == OrderStatus.PAID:
    ...
```

#### 2. 通用 Enum（跨模块）

放在：

```text
app/common/enums/
```

#### 示例（错误类 tail 枚举）

错误响应用的数字码见**第十二节**：`IntEnum` 只存 **AA BB CCC 合成的 tail**，服务号 **SS** 由环境变量 **`SERVICE_CODE`** 与 **`ErrorCodeBuilder`** 在运行时合成，**勿**在 Enum 里写完整九位码。

### 三、禁止行为（非常重要）

#### 1. 不要全部放 common

```text
common/enums/order_status.py   ❌
common/enums/user_status.py    ❌
```

原因：

* common 会变「垃圾桶」
* 业务边界混乱
* 后期无法拆分模块

#### 2. 不要放在数据库层

```text
infrastructure/db/models/order_status.py   ❌
```

原因：

* enum 不属于数据库实现
* 会导致业务逻辑污染

#### 3. 枚举类型定义用标准库

业务/通用枚举定义使用：

```python
from enum import Enum
```

不要用 SQLAlchemy 的 `Enum` 类型来**定义**业务枚举本体；ORM 列映射见下文「ORM 使用规范」。

### 四、ORM 使用规范（SQLAlchemy）

#### 推荐写法（最稳）

```python
status = Column(Integer, default=OrderStatus.PENDING.value)
```

#### 可选写法（不推荐新手）

```python
from sqlalchemy import Enum as SAEnum

status = Column(SAEnum(OrderStatus))
```

注意：存在跨数据库兼容与 Alembic 迁移复杂度风险。

### 五、Pydantic / FastAPI 使用

返回值中可直接使用枚举类型，便于序列化：

```python
class OrderResponse(BaseModel):
    status: OrderStatus
```

`int` 型枚举常见 JSON 输出为数字；若需字符串，可使用：

```python
class OrderStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
```

### 六、命名规范

* 文件名：`order_status.py`、`user_type.py`、`payment_status.py`
* 类名：`OrderStatus`、`UserType`、`PaymentStatus`
* 成员：`PENDING`、`PAID`、`CANCELLED`

### 七、依赖方向（必须遵守）

```text
Enum → 被 Model / Service 等引用（被依赖）
```

禁止：

```text
Enum → 依赖 Model ❌
```

### 八、设计判断标准

创建 Enum 前自问：**这是业务规则吗？**

| 类型 | 放置 |
| ---- | ---- |
| 业务状态 | `application/enums/` 或 `domain/.../enums.py` |
| 通用 / 系统错误码 | `common/enums/error_code.py`（见第十二节） |
| 业务错误码（按模块） | `application/{module}/errors.py`（见第十二节） |
| HTTP 相关通用 | `common/enums/` |
| 纯数据库存储细节 | 不应单独成「业务枚举」源 |

### 九、推荐结构（摘要）

```text
app/
├── application/
│   └── enums/
│       ├── order_status.py
│       ├── user_status.py
│       └── payment_status.py
│
├── common/
│   └── enums/
│       └── error_code.py
```

### 十、一句话总结

> Enum 放哪里，不看「谁用它」，只看「谁定义它」

* 业务定义 → application / domain
* 通用定义 → common
* **永远不要**把枚举定义放在 infrastructure（含 db models 目录作为唯一「业务语义」源）

---

## 十二、错误码与异常体系（ErrorCode + Exception）

### 一、核心约定（必须遵守）

1. **完整九位对外码**只能由 **`ErrorCodeBuilder`** 生成；**禁止**在业务里手写 `SS * 10**7 + …` 或自行拼接九位字符串/整数。
2. **`IntEnum` 只定义「业务低位」**：成员值为 **tail** = `AA × 10⁵ + BB × 10³ + CCC`，**不包含服务号 SS**。SS 来自环境变量 **`SERVICE_CODE`**（0–99，见 `config.service.ServiceSettings`），由 **`ErrorCodeBuilder.build(tail)`** 与 tail 合成最终整数；展示用 `f"{full:09d}"`。
3. **tail 的 AA 段**仅允许 **10**（业务）、**20**（系统）、**30**（第三方）；应用 **`ErrorCodeBuilder.compose_tail(aa=…, bb=…, ccc=…)`** 生成 tail，避免散落魔法公式。
4. **业务失败**必须 **`raise BizException(业务错误枚举, message)`**；**系统 / 基础设施 / 第三方调用失败**用 **`raise SystemException(系统类枚举, message)`**。不要在 Service 里直接 `return JsonResponse.error(...)` 代替异常（除非极薄适配层且团队明确允许）。
5. **所有异常**须进入 **全局 `exception_handler`**（如 `app/interfaces/api/exception_handlers.py`），由 handler 统一转 **`JsonResponse`** 与 HTTP 状态码；**禁止**在 endpoint 大面积 `try/except` 吞掉 `BizException` / `SystemException` 且不向上抛。

九位语义（合成后整型 `full`）：

```text
full = SS × 10⁷ + tail，其中 tail = AA × 10⁵ + BB × 10³ + CCC
```

示例：`SERVICE_CODE=2`，订单业务 `AA=10, BB=1, CCC=1` → tail=`1001001`，full=`21001001`，字符串 **`021001001`**。

### 二、通用错误 tail（系统类）

路径：

```text
app/common/enums/error_code.py
```

成员为 **AA=20** 的 tail（如 `NOT_FOUND`、`INTERNAL_ERROR`），**不得**含 SS。

```python
from enum import IntEnum
from app.common.exceptions.error_code_builder import ErrorCodeBuilder

class ErrorCode(IntEnum):
    NOT_FOUND = ErrorCodeBuilder.compose_tail(aa=20, bb=0, ccc=404)
    INTERNAL_ERROR = ErrorCodeBuilder.compose_tail(aa=20, bb=0, ccc=500)
```

### 三、业务模块错误 tail

路径：

```text
app/application/{module}/errors.py
```

成员 **仅 AA=10**（业务），供 **`BizException`** 使用。

```python
from enum import IntEnum
from app.common.exceptions.error_code_builder import ErrorCodeBuilder

class OrderErrorCode(IntEnum):
    ORDER_NOT_EXIST = ErrorCodeBuilder.compose_tail(aa=10, bb=1, ccc=1)
```

### 四、分段职责与登记（必须）

| 段 | 含义 | 约定 |
| -- | ---- | ---- |
| SS | 服务 | 环境变量 **`SERVICE_CODE`**，部署时按服务登记 |
| AA | 类型 | **10 / 20 / 30**（业务 / 系统 / 第三方） |
| BB | 模块 | 服务内子域 `00–99`，须文档登记 |
| CCC | 序号 | `000–999`，同一 `(SS, AA, BB)` 下递增 |

从**完整码**反解：`SS = full // 10⁷ % 100`，`tail = full % 10⁷`，再对 tail 拆 AA/BB/CCC。

### 五、异常与 Handler

| 类型 | 抛出 | 枚举 AA |
| ---- | ---- | ------- |
| 业务规则 / 领域校验失败 | `BizException` | 10 |
| DB/Redis/向量库/未预期缺陷、第三方超时等 | `SystemException` | 20 或 30 |

在 `create_app()` 中注册 **`register_exception_handlers(app)`**；兜底 **`Exception`** handler 将未捕获异常记录日志并返回 `INTERNAL_ERROR` 合成码（仍经 `ErrorCodeBuilder`）。

### 六、禁止行为

* 手写完整九位码或手写 `SS` 与 tail 拼接 ❌（须 `ErrorCodeBuilder`）
* 在 `IntEnum` 中写入 **SS** ❌
* 业务失败不用 `BizException`、系统问题不用 `SystemException` ❌
* 绕过全局 handler、在接口层随意吞异常 ❌
* 把所有业务错误 tail 堆在单一文件 ❌（按模块 `errors.py` 拆分）
* 纯字符串作唯一错误标识 ❌
* 错误枚举定义放在 `infrastructure/` ❌

### 七、模块化目录（推荐）

```text
app/application/{module}/
├── service.py
├── errors.py          # 业务 tail 枚举（AA=10）+ BizException 抛出点
├── enums.py           # 可选
├── schemas.py         # 可选
```

```text
app/common/exceptions/
├── error_code_builder.py
├── app_exceptions.py   # BizException / SystemException
```

```text
app/interfaces/api/exception_handlers.py
```

### 八、一句话

> **tail 进 Enum，SS 进 env，完整码只经 ErrorCodeBuilder；业务抛 BizException，系统抛 SystemException，统一走全局 handler。**
