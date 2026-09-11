"""验证 main 数据库 ORM 元数据和命名约定。"""

from sqlalchemy import DateTime, DefaultClause, Integer, String

from app.contexts.user.infrastructure.persistence.models.user import UserModel
from app.infrastructure.database.orm.main import MainBase
from app.infrastructure.queue.failed.sql.model import FailedJobModel
from database.main.model_registry import load_main_database_metadata


def test_main_database_model_registry_loads_user_model() -> None:
    metadata = load_main_database_metadata()
    users_table = UserModel.__table__

    assert metadata is MainBase.metadata
    assert UserModel.__tablename__ == "users"
    assert users_table is metadata.tables["users"]
    assert users_table.primary_key.name == "pk_users"
    assert users_table.comment == "用户信息"
    assert isinstance(users_table.c.id.type, String)
    assert users_table.c.id.type.length == 36
    assert isinstance(users_table.c.created_at.type, DateTime)
    assert isinstance(users_table.c.updated_at.type, DateTime)
    assert users_table.c.created_at.type.timezone is False
    assert users_table.c.updated_at.type.timezone is False
    assert isinstance(users_table.c.version.type, Integer)
    assert users_table.c.version.nullable is False
    assert isinstance(users_table.c.version.server_default, DefaultClause)
    assert str(users_table.c.version.server_default.arg) == "1"
    assert {column.name: column.comment for column in users_table.columns} == {
        "id": "用户 ID",
        "username": "用户名",
        "email": "邮箱地址",
        "password": "密码哈希",
        "status": "用户状态",
        "created_at": "创建时间",
        "updated_at": "更新时间",
        "version": "并发版本",
    }


def test_main_database_model_registry_loads_queue_failed_job_model() -> None:
    metadata = load_main_database_metadata()
    failed_jobs_table = FailedJobModel.__table__

    assert failed_jobs_table is metadata.tables["queue_failed_jobs"]
    assert failed_jobs_table.primary_key.name == "pk_queue_failed_jobs"
    assert failed_jobs_table.comment == "队列失败任务记录"
    assert {column.name: column.comment for column in failed_jobs_table.columns} == {
        "failure_id": "失败记录 ID",
        "job_id": "原任务 ID，非法信封时为空",
        "payload": "原始任务信封",
        "connection": "队列连接名",
        "queue": "逻辑队列名",
        "failed_at": "最终失败时间",
        "attempts": "本次投递执行次数",
        "reason": "失败原因分类",
        "error_type": "异常类型，不含异常消息",
        "stacktrace": "安全调用栈位置",
    }
