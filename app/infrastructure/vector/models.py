"""定义跨向量驱动共享的数据、集合和检索值对象。"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

from app.infrastructure.vector.errors import VectorConfigurationError

type MetadataScalar = str | int | float | bool
type VectorMetadata = Mapping[str, MetadataScalar]
type VectorFilters = Mapping[str, MetadataScalar]

_COLLECTION_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
_METADATA_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESERVED_METADATA_KEYS = frozenset(("id", "vector", "_vector_dimension", "_vector_metric", "_vector_record"))


class VectorMetric(StrEnum):
    """声明公共向量距离或相似度算法。"""

    COSINE = "cosine"
    DOT_PRODUCT = "dot_product"
    L2 = "l2"


@dataclass(frozen=True, slots=True)
class VectorCollectionSpec:
    """描述创建跨驱动 Collection 所需的可移植配置。"""

    name: str
    dimension: int
    metric: VectorMetric = VectorMetric.COSINE

    def __post_init__(self) -> None:
        """拒绝各内置驱动无法共同接受的名称和维度。"""

        _validate_collection_name(self.name)
        if not 1 <= self.dimension <= 4_096:
            raise VectorConfigurationError("向量维度必须在 1 到 4096 之间")


@dataclass(frozen=True, slots=True)
class VectorCollectionInfo:
    """返回 Collection 的公共名称、维度和距离配置。"""

    name: str
    dimension: int
    metric: VectorMetric


@dataclass(frozen=True, slots=True)
class VectorPoint:
    """保存一个由调用方生成的向量及可过滤元数据。"""

    id: str
    vector: tuple[float, ...]
    metadata: VectorMetadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 ID、有限向量值和公共元数据子集。"""

        if not self.id or len(self.id.encode("utf-8")) > 512:
            raise VectorConfigurationError("向量 ID 的 UTF-8 长度必须在 1 到 512 字节之间")
        _validate_vector(self.vector)
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True)
class VectorMatch:
    """返回按相关度降序排列的单个向量命中。"""

    id: str
    score: float
    metadata: VectorMetadata = field(default_factory=dict)


def validate_collection_name(name: str) -> None:
    """校验 Collection 名称满足三个内置驱动的公共约束。"""

    _validate_collection_name(name)


def validate_filters(filters: VectorFilters | None) -> None:
    """校验只包含顶层等值条件的可移植过滤器。"""

    if filters is not None:
        _validate_metadata(filters)


def validate_limit(limit: int) -> None:
    """限制单次相似度检索返回数量。"""

    if not 1 <= limit <= 10_000:
        raise VectorConfigurationError("向量检索 limit 必须在 1 到 10000 之间")


def validate_query_vector(vector: tuple[float, ...]) -> None:
    """校验查询向量非空且全部为有限数值。"""

    _validate_vector(vector)


def _validate_collection_name(name: str) -> None:
    if not 3 <= len(name) <= 63 or _COLLECTION_NAME.fullmatch(name) is None:
        raise VectorConfigurationError("Collection 名称必须为 3 到 63 位小写字母、数字、下划线或连字符，且首尾为字母或数字")


def _validate_vector(vector: tuple[float, ...]) -> None:
    if not vector:
        raise VectorConfigurationError("向量不能为空")
    if any(isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value) for value in vector):
        raise VectorConfigurationError("向量只能包含有限数值")


def _validate_metadata(metadata: Mapping[str, MetadataScalar]) -> None:
    for key, value in metadata.items():
        if len(key) > 128 or _METADATA_KEY.fullmatch(key) is None:
            raise VectorConfigurationError("元数据字段名必须为 1 到 128 位字母、数字或下划线，且不能以数字开头")
        if key in _RESERVED_METADATA_KEYS:
            raise VectorConfigurationError(f"元数据字段名 {key!r} 为向量接口保留字段")
        if not isinstance(value, str | int | float | bool) or (isinstance(value, float) and not isfinite(value)):
            raise VectorConfigurationError(f"元数据字段 {key!r} 只能使用有限标量值")
