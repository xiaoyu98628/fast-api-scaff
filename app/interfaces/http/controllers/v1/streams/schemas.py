"""定义事件流查询参数及发送前的校验规则。"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EventStreamParams(BaseModel):
    """限制事件流长度，并确保模拟失败位置位于本次数据流中。"""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(default=5, ge=1, le=20, description="计划发送的消息数量")
    fail_at: int | None = Field(default=None, ge=1, le=20, description="模拟处理失败的消息序号，不得超过 count")

    @model_validator(mode="after")
    def validate_failure_position(self) -> Self:
        """在响应开始前拒绝超出消息范围的失败位置。"""

        if self.fail_at is not None and self.fail_at > self.count:
            raise ValueError("fail_at 不能超过 count")
        return self
