import httpx
from typing import Dict, Any, Optional
from .settings import settings

DEFAULT_HEADERS = {
    "accept": "*/*",
    "x-requested-with": "XMLHttpRequest",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 TrainTracker/2.0",
    "referer": "https://trainfinder.otenko.com/home/nextlevel",
}

class TrainFinderClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            proxies = None
            if settings.HTTP_PROXY_URL:
                proxies = {
                    "http://": settings.HTTP_PROXY_URL,
                    "https://": settings.HTTP_PROXY_URL,
                }
            self._client = httpx.AsyncClient(proxies=proxies, timeout=30.0, follow_redirects=True)
        return self._client

    async def fetch_viewport(self) -> Dict[str, Any]:
        client = await self._ensure_client()
        cookies = {".ASPXAUTH": settings.TRAINFINDER_ASPXAUTH}
        r = await client.get(
            settings.TRAINFINDER_VIEWPORT_URL,
            headers=DEFAULT_HEADERS,
            cookies=cookies,
        )
        r.raise_for_status()
        # TrainFinder usually returns JSON. If it returns text, httpx will raise on .json()
        return r.json()

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

client = TrainFinderClient()
