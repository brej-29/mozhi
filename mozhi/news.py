"""Headlines from Google News RSS, in the visitor's language. Headlines and links only.

Browsers block this feed (no CORS), so it works in the desktop app and not on the hosted page.
"""

import xml.etree.ElementTree as ET

import httpx

FEEDS = {
    "en": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    "ta": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=ta&gl=IN&ceid=IN:ta",
    "ml": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=ml&gl=IN&ceid=IN:ml",
}
MAX_BYTES = 400_000


def parse(xml: bytes, limit: int = 5) -> list[dict]:
    items = []
    for it in ET.fromstring(xml).iter("item"):
        title, link = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        if title and link.startswith("https://"):
            items.append({"title": title, "source": src, "url": link})
        if len(items) == limit:
            break
    return items


async def headlines(lang: str = "en", client: httpx.AsyncClient | None = None) -> list[dict]:
    """[] when the feed is unreachable or malformed."""
    try:
        async with (client or httpx.AsyncClient(timeout=8, follow_redirects=True)) as c:
            r = await c.get(FEEDS.get(lang, FEEDS["en"]))
            r.raise_for_status()
            return parse(r.content[:MAX_BYTES]) if len(r.content) <= MAX_BYTES else []
    except (httpx.HTTPError, ET.ParseError):
        return []
