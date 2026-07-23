import pytest

from app.services.research import UnsafeUrl, validate_external_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://127.0.0.1/private",
        "https://10.0.0.1/",
        "https://[::1]/",
        "https://user:pass@example.com/",
        "https://example.com:444/",
    ],
)
async def test_unsafe_research_urls_are_blocked(url):
    with pytest.raises(UnsafeUrl):
        await validate_external_url(url)
