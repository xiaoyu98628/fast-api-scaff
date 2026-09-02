from dataclasses import dataclass

from pydantic import BaseModel

from app.interfaces.http.shared.pagination import build_page_response
from app.interfaces.shared.pagination import PageInput


@dataclass(frozen=True, slots=True)
class SourceItem:
    value: int


class ResponseItem(BaseModel):
    value: int


def map_item(item: SourceItem) -> ResponseItem:
    return ResponseItem(value=item.value)


def test_build_page_response_maps_items_and_builds_meta() -> None:
    response = build_page_response(
        items=(SourceItem(1), SourceItem(2)),
        total=21,
        pagination=PageInput(page=2, limit=10),
        item_mapper=map_item,
    )

    assert response.model_dump() == {
        "items": [{"value": 1}, {"value": 2}],
        "meta": {
            "page": 2,
            "limit": 10,
            "total": 21,
            "total_pages": 3,
        },
    }


def test_build_page_response_handles_empty_result() -> None:
    response = build_page_response(
        items=(),
        total=0,
        pagination=PageInput(page=1, limit=20),
        item_mapper=map_item,
    )

    assert response.model_dump() == {
        "items": [],
        "meta": {
            "page": 1,
            "limit": 20,
            "total": 0,
            "total_pages": 0,
        },
    }
