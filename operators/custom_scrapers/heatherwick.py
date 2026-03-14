# operators/custom_scrapers/heatherwick.py
"""
Heatherwick Studio Custom Scraper
Site: https://heatherwick.com
Strategy: HTTP + BeautifulSoup — scrape the HOMEPAGE (not /studio/news/)

Why homepage? The /studio/news/ page is fully JS-rendered (empty HTML).
But the homepage renders the 5 most recent news articles server-side
with dates, titles, excerpts, and links.

Dates: "28 February 2026" format (%d %B %Y)
Links: /studio/news/article-slug/
CMS: WordPress (images from /wp-content/uploads/)
"""

import asyncio
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class HeatherwickScraper(StudioHttpScraper):
    source_id = "heatherwick"
    source_name = "Heatherwick Studio"
    base_url = "https://heatherwick.com"
    # Scrape the homepage — it renders 5 recent news items server-side
    news_url = "https://heatherwick.com/"

    # CSS selectors
    # Homepage news items are <a> tags linking to /studio/news/slug/
    card_selector = "a[href*='/studio/news/']"
    title_selector = "h2"
    link_selector = ""  # Card itself is the <a> link
    date_selector = ""  # Date parsed via override below
    date_format = "%d %B %Y"  # "28 February 2026"
    image_selector = "img"

    # URL filtering
    excluded_patterns = [
        "/studio/news/$",
        "/studio/news#",
    ]

    def _is_valid_article_url(self, url: str) -> bool:
        """Only accept article URLs with a slug after /studio/news/."""
        if not super()._is_valid_article_url(url):
            return False
        # Must have something after /studio/news/
        path = url.split("heatherwick.com")[-1] if "heatherwick.com" in url else url
        path = path.rstrip("/")
        if path == "/studio/news" or path == "":
            return False
        return "/studio/news/" in url

    def _extract_date(self, card):
        """
        Extract date from card text.

        On the homepage, each news <a> card contains the date as plain text
        like "28 February 2026" before the <h2> title. We look for text nodes
        that match a date pattern.
        """
        import re

        # Get all text content from the card
        full_text = card.get_text(separator="\n", strip=True)

        # Look for date pattern: "DD Month YYYY" (e.g. "28 February 2026")
        date_pattern = r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})'
        match = re.search(date_pattern, full_text)
        if match:
            return self._parse_date_text(match.group(1))

        return None


# Register
custom_scraper_registry.register(HeatherwickScraper)
