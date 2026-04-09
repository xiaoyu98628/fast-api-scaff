"""订单模块业务错误码定义（code + message + status_code）。"""

from enum import IntEnum


class OrderErrorCode(IntEnum):
    """订单业务码（XXXXX）。"""

    ORDER_NOT_EXIST = 2001
    ORDER_ALREADY_PAID = 2002

    def message(self) -> str:
        return {
            OrderErrorCode.ORDER_NOT_EXIST: "订单不存在",
            OrderErrorCode.ORDER_ALREADY_PAID: "订单已支付",
        }[self]

    def status_code(self) -> int:
        return {
            OrderErrorCode.ORDER_NOT_EXIST: 404,
            OrderErrorCode.ORDER_ALREADY_PAID: 400,
        }[self]
