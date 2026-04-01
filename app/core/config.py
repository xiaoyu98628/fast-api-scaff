import threading

from app.Singleton import Singleton


class Config(metaclass=Singleton):
    """
    配置类
    """

    _init_lock = threading.Lock()

    def __init__(self):
        self._initialized = False