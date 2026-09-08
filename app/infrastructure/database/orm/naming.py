"""为 Alembic 和数据库约束提供跨环境稳定的命名规则。"""

# 显式名称让迁移可以可靠引用并删除约束，避免依赖数据库自动命名。
CONSTRAINT_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
