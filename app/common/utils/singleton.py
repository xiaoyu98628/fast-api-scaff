"""线程安全的单例元类；需要进程内唯一实例的客户端类可使用 ``metaclass=Singleton``。"""

from threading import Lock


class Singleton(type):
    """每个使用本元类的 **类** 各自持有一个共享实例（非全局一个大单例）。"""

    _instances: dict[type, object] = {}
    _locks: dict[type, Lock] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            if cls not in cls._locks:
                cls._locks[cls] = Lock()
            with cls._locks[cls]:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
