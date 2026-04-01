from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine


app = FastAPI()


# 创建一步引擎

DATABASE_URL = "mysql+aiomysql://用户名:密码@连接地址:3306/数据库名?charset=utf8"
engine = create_async_engine(
    DATABASE_URL,
    echo=True, # 可选，输出 SQL 日志
    pool_size=10, # 设置连接池活跃的连接数
    max_overflow=20, # 允许额外的连接数
)
