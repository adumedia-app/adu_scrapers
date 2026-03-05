# operators/custom_scrapers/studio_gang.py
"""
Studio Gang Custom Scraper
Site: https://studiogang.com/now/news/
Strategy: HTTP + BeautifulSoup (WordPress, server-side rendered)
Dates: No dates visible on listing page — relies on article tracker
Links: /now/article-slug/
Notes: WordPress site but RSS feed is broken. Active studio with regular posts.
       Article cards have category ("News"), title, image, description excerpt.
       Can also try WP REST API at /wp-json/wp/v2/posts as alternative.
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class StudioGangScraper(StudioHttpScraper):
    source_id = "studio_gang"
    source_name = "Studio Gang"
    base_url = "https://studiogang.com"
    news_url = "https://studiogang.com/now/news/"

    # WordPress with server-side rendered cards
    card_selector = "article, .post, .card, a[href*='/now/']"
    title_selector = "h2, h3"
    link_selector = "a"
    date_selector = "time, .date, .post-date, span"
    date_format = ""  # No dates on listing — tracker handles it
    image_selector = "img"

    excluded_patterns = [
        "/now/news/$",
        "/now/news$",
        "/now/$",
        "/now$",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        # Studio Gang articles: /now/article-slug/
        path = url.split("studiogang.com")[-1] if "studiogang.com" in url else url
        path = path.rstrip("/")
        if path in ["/now", "/now/news"]:
            return False
        return "/now/" in url


custom_scraper_registry.register(StudioGangScraper)
