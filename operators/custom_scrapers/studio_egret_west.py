# operators/custom_scrapers/studio_egret_west.py
"""
Studio Egret West Custom Scraper
Site: https://studioegretwest.com/news
Strategy: HTTP + BeautifulSoup (Craft CMS, server-side rendered, clean HTML)
Dates: "Feb 20, 2026" format (Mon DD, YYYY)
Links: /news/article-slug
Notes: Active posting (several times/month). UK-based practice.
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class StudioEgretWestScraper(StudioHttpScraper):
    source_id = "studio_egret_west"
    source_name = "Studio Egret West"
    base_url = "https://studioegretwest.com"
    news_url = "https://studioegretwest.com/news"

    card_selector = "article, .card, .entry, a[href*='/news/']"
    title_selector = "h2, h3"
    link_selector = "a"
    date_selector = "time, .date, span"
    date_format = "%b %d, %Y"  # "Feb 20, 2026"
    image_selector = "img"

    excluded_patterns = [
        "/news$",
        "/news/$",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        return "/news/" in url and url.rstrip("/") != self.news_url


custom_scraper_registry.register(StudioEgretWestScraper)
