# operators/custom_scrapers/mvrdv.py
"""
MVRDV Custom Scraper
Site: https://www.mvrdv.com/news
Strategy: HTTP + BeautifulSoup (server-side rendered)
Notes: Use /news not /updates (which mixes events). Links: /news/4844/article-slug
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class MvrdvScraper(StudioHttpScraper):
    source_id = "mvrdv"
    source_name = "MVRDV"
    base_url = "https://www.mvrdv.com"
    news_url = "https://www.mvrdv.com/news"

    # CSS selectors — verify against live site
    card_selector = "article, .card, a[href*='/news/']"
    title_selector = "h2, h3"
    link_selector = "a"
    date_selector = "time, .date, span"
    date_format = ""  # Relative dates ("8 days") — will fall through to tracker-based detection
    image_selector = "img"

    excluded_patterns = [
        "/events/",
        "/updates/",
        "/news$",
        "/news/$",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        # MVRDV articles: /news/NNNN/slug
        return "/news/" in url and url.rstrip("/") != self.news_url


custom_scraper_registry.register(MvrdvScraper)
