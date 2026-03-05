# operators/custom_scrapers/david_chipperfield.py
"""
David Chipperfield Architects Custom Scraper
Site: https://davidchipperfield.com/news
Strategy: HTTP + BeautifulSoup (server-side rendered, clean <ol> list)
Dates: DD.MM.YYYY format
Links: /news/YYYY/article-slug
Notes: Very clean minimal HTML. Low frequency (~1-2/month). Target "Recent news" section only.
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class DavidChipperfieldScraper(StudioHttpScraper):
    source_id = "david_chipperfield"
    source_name = "David Chipperfield Architects"
    base_url = "https://davidchipperfield.com"
    news_url = "https://davidchipperfield.com/news"

    # CSS selectors — clean <ol> list with link text titles and dates
    card_selector = "ol li, .news-item, article"
    title_selector = "a"
    link_selector = "a"
    date_selector = "time, .date, span"
    date_format = "%d.%m.%Y"
    image_selector = ""  # Minimal listing — no images on news list

    excluded_patterns = [
        "/press-cuttings/",
        "/writing/",
        "/publications/",
        "/news$",
        "/news/$",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        return "/news/" in url and url.rstrip("/") != self.news_url


custom_scraper_registry.register(DavidChipperfieldScraper)
