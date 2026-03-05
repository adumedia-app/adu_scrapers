# operators/custom_scrapers/snohetta.py
"""
Snøhetta Custom Scraper
Site: https://www.snohetta.com/news
Strategy: HTTP + BeautifulSoup (server-side rendered, clean HTML)
Dates: "05 March 2026" format
Links: /news/article-slug
Images: Bunny CDN (snohetta.b-cdn.net)
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class SnohettaScraper(StudioHttpScraper):
    source_id = "snohetta"
    source_name = "Snøhetta"
    base_url = "https://www.snohetta.com"
    news_url = "https://www.snohetta.com/news"

    # CSS selectors — verify against live site
    card_selector = "article, .card, a[href*='/news/']"
    title_selector = "h2, h3"
    link_selector = "a"
    date_selector = "time, .date, span"
    date_format = "%d %B %Y"  # "05 March 2026"
    image_selector = "img"

    excluded_patterns = [
        "/news$",
        "/news/$",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        path = url.split("snohetta.com")[-1] if "snohetta.com" in url else url
        path = path.rstrip("/")
        if path == "/news" or path == "":
            return False
        return "/news/" in url


custom_scraper_registry.register(SnohettaScraper)
