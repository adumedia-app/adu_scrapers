# operators/custom_scrapers/gmp.py
"""
gmp · Architekten von Gerkan, Marg and Partners Custom Scraper
Site: https://www.gmp.de/en/news/41/press/
Strategy: HTTP + BeautifulSoup (server-side rendered)

HTML structure:
    Cards are div.project__item.clickable-block with data-href attribute
    (NOT regular <a href> links — requires _extract_link override)

Dates: "Mar. 10, 2026" / "Jan. 15, 2026" (abbreviated month with period)
Links: /en/news/41/press/{id}/{slug}
"""

import re
from typing import Optional
from bs4 import Tag

from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class GmpScraper(StudioHttpScraper):
    source_id = "gmp"
    source_name = "gmp Architekten"
    base_url = "https://www.gmp.de"
    news_url = "https://www.gmp.de/en/news/41/press/"

    # CSS selectors
    card_selector = "div.project__item.clickable-block"
    title_selector = "h2, h3, .project__item-title, .title"
    link_selector = ""  # Link is in data-href, handled by override
    date_selector = ""  # Date parsed via override
    date_format = "%b %d, %Y"  # "Mar 10, 2026" (after stripping period)
    image_selector = "img"

    # URL filtering
    excluded_patterns = [
        "/news/41/press/$",
        "/news/41/press/#",
    ]

    def _extract_link(self, card: Tag) -> Optional[str]:
        """
        Extract link from data-href attribute.
        gmp uses clickable-block divs with data-href instead of <a> tags.
        """
        # Primary: data-href attribute on the card itself
        data_href = card.get("data-href")
        if data_href:
            return data_href

        # Fallback: standard <a> tag
        a_tag = card.find("a", href=True)
        if a_tag:
            return a_tag["href"]

        return None

    def _extract_date(self, card: Tag) -> Optional[str]:
        """
        Extract date from card text.

        gmp dates appear as "Mar. 10, 2026" or "Jan. 15, 2026" —
        abbreviated month with a trailing period.
        We search all text in the card for this pattern.
        """
        full_text = card.get_text(separator="\n", strip=True)

        # Pattern: "Mon. DD, YYYY" (e.g., "Mar. 10, 2026")
        date_pattern = r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+\d{4})'
        match = re.search(date_pattern, full_text)
        if match:
            date_text = match.group(1)
            # Remove period after month abbreviation: "Mar." → "Mar"
            date_text = re.sub(r'(\w{3})\.', r'\1', date_text)
            # Ensure comma is present: "Mar 10, 2026"
            if ',' not in date_text:
                date_text = re.sub(r'(\d{1,2})\s+(\d{4})', r'\1, \2', date_text)
            return self._parse_date_text(date_text)

        return None

    def _is_valid_article_url(self, url: str) -> bool:
        """Only accept press article URLs with an ID and slug."""
        if not super()._is_valid_article_url(url):
            return False
        # Must match pattern: /en/news/41/press/{id}/{slug}
        # or at minimum have something after /press/
        path = url.split("gmp.de")[-1] if "gmp.de" in url else url
        path = path.rstrip("/")
        # Reject the listing page itself
        if path.endswith("/press") or path.endswith("/41"):
            return False
        # Must contain /press/ followed by more path
        if "/press/" not in path:
            return False
        # Should have a numeric ID after /press/
        press_suffix = path.split("/press/")[-1]
        if not press_suffix or not press_suffix.split("/")[0].isdigit():
            return False
        return True


# Register
custom_scraper_registry.register(GmpScraper)
