# operators/custom_scrapers/big.py
"""
BIG (Bjarke Ingels Group) Custom Scraper
Site: https://big.dk/news
Strategy: HTTP + BeautifulSoup (server-side rendered, clean HTML)
Dates: DD.MM.YYYY format
Links: /news/article-slug
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class BigScraper(StudioHttpScraper):
    source_id = "big"
    source_name = "BIG"
    base_url = "https://big.dk"
    news_url = "https://big.dk/news"

    # CSS selectors — verify against live site, adjust if needed
    card_selector = "a[href*='/news/']"  # Article link cards
    title_selector = "h2"
    link_selector = ""  # Card itself is the link
    date_selector = "time, .date, span"
    date_format = "%d.%m.%Y"
    image_selector = "img"

    # URL filtering
    excluded_patterns = [
        "/news$",
        "/news/$",
        "/news#",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        """BIG articles: /news/article-slug (not just /news)"""
        if not super()._is_valid_article_url(url):
            return False
        # Must have something after /news/
        path = url.split("big.dk")[-1] if "big.dk" in url else url
        path = path.rstrip("/")
        if path == "/news" or path == "":
            return False
        return "/news/" in url


# Register
custom_scraper_registry.register(BigScraper)
