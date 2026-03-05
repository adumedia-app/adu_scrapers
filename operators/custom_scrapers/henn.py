# operators/custom_scrapers/henn.py
"""
HENN Custom Scraper
Site: https://www.henn.com/en/news
Strategy: HTTP + BeautifulSoup (Drupal CMS, server-side rendered)
Dates: DD.MM.YYYY format
Links: /en/news/article-slug
Notes: Filter for "NEWS" category (skip "PODCAST" items).
       Images from /sites/default/files/styles/ (Drupal pattern).
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class HennScraper(StudioHttpScraper):
    source_id = "henn"
    source_name = "HENN"
    base_url = "https://www.henn.com"
    news_url = "https://www.henn.com/en/news"

    # CSS selectors — Drupal with clear article cards
    card_selector = "article, .views-row, .node, .card"
    title_selector = "h2, h3"
    link_selector = "a"
    date_selector = "time, .date, .field--name-field-date, span"
    date_format = "%d.%m.%Y"
    image_selector = "img"

    # Category filtering — skip PODCAST items
    category_selector = ".field--name-field-category, .category, .tag"
    allowed_categories = ["news"]

    excluded_patterns = [
        "/en/news$",
        "/en/news/$",
        "/en/podcast/",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        return "/en/news/" in url


custom_scraper_registry.register(HennScraper)
