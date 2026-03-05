# operators/custom_scrapers/shl.py
"""
Schmidt Hammer Lassen (SHL) Custom Scraper
Site: https://www.shl.dk/en/agendas-insights
Strategy: HTTP + BeautifulSoup (server-side rendered, clean HTML with dates)
Dates: DD.MM.YYYY format
Links: /en/agendas-insights/article-slug
Notes: Bilingual (Danish/English) — use /en/ path. ~2-3 posts/month.
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class ShlScraper(StudioHttpScraper):
    source_id = "shl"
    source_name = "Schmidt Hammer Lassen"
    base_url = "https://www.shl.dk"
    news_url = "https://www.shl.dk/en/agendas-insights"

    card_selector = "article, .card, .insight-item, a[href*='/agendas-insights/']"
    title_selector = "h2, h3"
    link_selector = "a"
    date_selector = "time, .date, span"
    date_format = "%d.%m.%Y"
    image_selector = "img"

    excluded_patterns = [
        "/en/agendas-insights$",
        "/en/agendas-insights/$",
        "/da/",  # Skip Danish pages
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        return "/en/agendas-insights/" in url


custom_scraper_registry.register(ShlScraper)
