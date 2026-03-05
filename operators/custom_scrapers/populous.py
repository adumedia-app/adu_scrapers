# operators/custom_scrapers/populous.py
"""
Populous Custom Scraper
Site: https://populous.com/news/
Strategy: HTTP + BeautifulSoup (server-side rendered, clean HTML)
Dates: "February 17, 2026" format (Month DD, YYYY)
Links: /article/article-slug
Notes: Very active (multiple times/week). Global sports/entertainment architecture.
       Categories: "News", "Magazine", "Perspectives" — filter for "News" only.
       607+ articles in archive across 51 pages (we only scrape first page).
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class PopulousScraper(StudioHttpScraper):
    source_id = "populous"
    source_name = "Populous"
    base_url = "https://populous.com"
    news_url = "https://populous.com/news/"

    card_selector = "article, .card, .news-item"
    title_selector = "h2, h3"
    link_selector = "a"
    date_selector = "time, .date, span"
    date_format = "%B %d, %Y"  # "February 17, 2026"
    image_selector = "img"

    # Filter for "News" category — skip "Magazine" and "Perspectives"
    category_selector = ".category, .tag, .type, .label"
    allowed_categories = ["news"]

    excluded_patterns = [
        "/news/$",
        "/news$",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        # Populous articles: /article/article-slug
        return "/article/" in url or "/news/" in url


custom_scraper_registry.register(PopulousScraper)
