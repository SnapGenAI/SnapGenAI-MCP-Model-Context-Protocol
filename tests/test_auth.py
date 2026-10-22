import pytest
from starlette.datastructures import Headers

from snapgen_mcp.auth import extract_api_key


def h(**kw):
    return Headers({k.replace("_", "-"): v for k, v in kw.items()})


@pytest.mark.parametrize("headers,expected", [
    (h(x_api_key="abc"), "abc"),
    (h(x_api_key="  abc  "), "abc"),
    (h(authorization="Bearer abc"), "abc"),
    (h(authorization="bearer abc"), "abc"),
    (h(authorization="BEARER   abc  "), "abc"),
    (h(x_api_key="from-header", authorization="Bearer from-bearer"), "from-header"),  # x-api-key wins
    (h(x_api_key="", authorization="Bearer fallback"), "fallback"),
    (h(authorization="Basic abc"), None),
    (h(authorization="Bearer"), None),
    (h(authorization="Bearer   "), None),
    (h(x_api_key="   "), None),
    (h(), None),
])
def test_extract_api_key(headers, expected):
    assert extract_api_key(headers) == expected


def test_header_names_are_case_insensitive():
    assert extract_api_key(Headers({"X-Api-Key": "k1"})) == "k1"
    assert extract_api_key(Headers({"AUTHORIZATION": "Bearer k2"})) == "k2"
