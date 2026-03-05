# operators/custom_scrapers/mecanoo.py
"""
Mecanoo Custom Scraper
Site: https://www.mecanoo.nl/News/Project-updates
Strategy: HTTP + BeautifulSoup (DotNetNuke CMS, server-side rendered)
Dates: No dates on listing page — relies on article tracker for "new" detection
Links: /News/ID/NNN/article-slug (sequential numeric IDs)
Notes: Sequential IDs make new article detection easy. Active posting frequency.
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class MecanooScraper(StudioHttpScraper):
    source_id = "mecanoo"
    source_name = "Mecanoo"
    base_url = "https://www.mecanoo.nl"
    news_url = "https://www.mecanoo.nl/News/Project-updates"

    # DotNetNuke CMS selectors
    card_selector = "article, .dnnFormItem, .news-item, .card, a[href*='/News/']"
    title_selector = "h2, h3, a"
    link_selector = "a"
    date_selector = ""  # No dates on listing page
    date_format = ""
    image_selector = "img"

    excluded_patterns = [
        "/News/Project-updates$",
        "/News/Project-updates/$",
        "/News$",
        "/News/$",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        # Mecanoo articles have numeric IDs: /News/ID/NNN/slug
        # Must have something after /News/ that's not just the listing page
        path = url.split("mecanoo.nl")[-1] if "mecanoo.nl" in url else url
        path = path.rstrip("/")
        if path in ["/News", "/News/Project-updates"]:
            return False
        return "/News/" in url


custom_scraper_registry.register(MecanooScraper)
