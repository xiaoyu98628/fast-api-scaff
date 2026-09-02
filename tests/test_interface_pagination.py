from app.interfaces.shared.pagination import (
    PageInput,
    PageMeta,
    PageOutput,
    calculate_total_pages,
)


def test_page_input_records_values_and_converts_to_offset() -> None:
    third_page = PageInput(page=3, limit=15)

    assert third_page.page == 3
    assert third_page.limit == 15
    assert third_page.offset == 30


def test_page_output_is_a_framework_neutral_immutable_value() -> None:
    meta = PageMeta(page=1, limit=20, total=21, total_pages=2)
    output = PageOutput(items=("alice",), meta=meta)

    assert output.items == ("alice",)
    assert output.meta == meta


def test_total_pages_is_derived_from_total_and_limit() -> None:
    assert calculate_total_pages(total=0, limit=15) == 0
    assert calculate_total_pages(total=1, limit=15) == 1
    assert calculate_total_pages(total=16, limit=15) == 2
