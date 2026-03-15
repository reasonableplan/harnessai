import pytest
from src.core.llm.json_extract import parse_json_response


def test_plain_json():
    result = parse_json_response('{"key": "value"}')
    assert result == {"key": "value"}


def test_json_in_code_block():
    text = '```json\n{"files": [], "summary": "done"}\n```'
    result = parse_json_response(text)
    assert result["summary"] == "done"


def test_json_with_surrounding_text():
    text = 'Here is the output:\n{"status": "ok"}\nThat is all.'
    result = parse_json_response(text)
    assert result["status"] == "ok"


def test_json_array():
    result = parse_json_response('[1, 2, 3]')
    assert result == [1, 2, 3]


def test_invalid_raises():
    with pytest.raises(ValueError):
        parse_json_response("no json here at all")
