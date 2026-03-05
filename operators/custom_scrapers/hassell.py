# operators/custom_scrapers/hassell.py
"""
Hassell Custom Scraper
Site: https://www.hassellstudio.com/insight/news
Strategy: HTTP + BeautifulSoup (server-side rendered, clean HTML)
Dates: "March 02, 2026" format (Month DD, YYYY)
Links: /news-event/article-slug (internal pages)
Notes: Two content types on listing page:
       - "News" → internal pages at /news-event/... (what we want)
       - "Media" → external links to Dezeen, ArchDaily etc. (skip these)
       Filter for "News" category only to avoid duplicating RSS sources.
       Australian firm. ~weekly frequency.
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class HassellScraper(StudioHttpScraper):
    source_id = "hassell"
    source_name = "Hassell"
    base_url = "https://www.hassellstudio.com"
    news_url = "https://www.hassellstudio.com/insight/news"

    card_selector = "article, .card, .insight-item, .news-item"
    title_selector = "h2, h3"
    link_selector = "a"
    date_selector = "time, .date, span"
    date_format = "%B %d, %Y"  # "March 02, 2026"
    image_selector = "img"

    # Filter for "News" category only — skip "Media" (external press links)
    category_selector = ".category, .tag, .type, .label"
    allowed_categories = ["news"]

    excluded_patterns = [
        "/insight/news$",
        "/insight/news/$",
        "/cn/",  # Skip Chinese version
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        # Only accept internal Hassell pages, skip external press links
        if "hassellstudio.com" not in url and url.startswith("http"):
            return False
        return True


custom_scraper_registry.register(HassellScraper)
