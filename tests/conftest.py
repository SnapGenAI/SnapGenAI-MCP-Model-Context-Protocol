import pytest

from snapgen_mcp import pricing


@pytest.fixture(autouse=True)
def no_live_price_list(monkeypatch):
    """Keep tests off the real price list. test_pricing.py puts the real fetcher back where it needs it."""
    async def unavailable(base_url):
        return None

    pricing._cache.clear()
    monkeypatch.setattr(pricing, "_fetch_table", unavailable)
    yield
    pricing._cache.clear()
