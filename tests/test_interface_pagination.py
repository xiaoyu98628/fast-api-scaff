from app.interfaces.shared.pagination import PageInput, PageOutput


def test_page_input_records_values_and_converts_to_offset() -> None:
    third_page = PageInput(page=3, limit=15)

    assert third_page.page == 3
    assert third_page.limit == 15
    assert third_page.offset == 30


def test_page_output_is_a_framework_neutral_immutable_value() -> None:
    output = PageOutput(items=("alice",), total=1, page=1, limit=20)

    assert output.items == ("alice",)
    assert output.total == 1
    assert output.page == 1
    assert output.limit == 20
