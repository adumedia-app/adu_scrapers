# operators/custom_scrapers/buro_ole_scheeren.py
"""
Büro Ole Scheeren Custom Scraper
Site: https://buro-os.com/news
Strategy: HTTP + BeautifulSoup (server-side rendered, clean HTML)
Notes: Has category tags (Award, Lecture, Announcement). Filter for news-relevant categories.
Links: /news/article-slug
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class BuroOleScheerenScraper(StudioHttpScraper):
    source_id = "buro_ole_scheeren"
    source_name = "Büro Ole Scheeren"
    base_url = "https://buro-os.com"
    news_url = "https://buro-os.com/news"

    # CSS selectors
    card_selector = "article, .card, .news-item, a[href*='/news/']"
    title_selector = "h2, h3"
    link_selector = "a"
    date_selector = "time, .date, span"
    date_format = ""  # Dates include location + date text — will try common formats
    image_selector = "img"

    # Category filtering — skip Lecture, Podcast items
    category_selector = ".category, .tag, .type"
    allowed_categories = ["announcement", "award", "news", "project"]

    excluded_patterns = [
        "/news$",
        "/news/$",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        return "/news/" in url and url.rstrip("/") != self.news_url


custom_scraper_registry.register(BuroOleScheerenScraper)
