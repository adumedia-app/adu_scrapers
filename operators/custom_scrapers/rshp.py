# operators/custom_scrapers/rshp.py
"""
RSHP (Rogers Stirk Harbour + Partners) Custom Scraper
Site: https://rshp.com/news/
Strategy: HTTP + BeautifulSoup (static HTML, table format)
Dates: DD.MM.YYYY format
Notes: Unusual table layout — very predictable and reliable parsing.
       Articles are self-contained on the news page (full descriptions included).
       Low posting frequency (~monthly).
"""

import asyncio
from bs4 import BeautifulSoup, Tag
from typing import List
from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class RshpScraper(StudioHttpScraper):
    source_id = "rshp"
    source_name = "RSHP"
    base_url = "https://rshp.com"
    news_url = "https://rshp.com/news/"

    # Table-based layout — try table rows first, fall back to generic selectors
    card_selector = "tr, article, .news-item"
    title_selector = "h2, h3, td a, a"
    link_selector = "a"
    date_selector = "time, .date, td"
    date_format = "%d.%m.%Y"
    image_selector = "img"

    excluded_patterns = [
        "/news/$",
        "/news$",
    ]

    def _extract_articles_from_soup(self, soup: BeautifulSoup) -> List[dict]:
        """
        Override for RSHP's table-based layout.
        Try table rows first, fall back to standard card extraction.
        """
        articles = []
        seen_urls = set()

        # Try table rows first
        rows = soup.select("table tr, tbody tr")
        if rows:
            print(f"[{self.source_id}] Found table with {len(rows)} rows")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 2:
                    continue  # Skip header or empty rows

                # Try to find link
                link_tag = row.find("a", href=True)
                if not link_tag:
                    continue

                url = self._resolve_url(link_tag["href"])
                if not self._is_valid_article_url(url) or url in seen_urls:
                    continue
                seen_urls.add(url)

                title = self._clean_text(link_tag.get_text(strip=True))
                if not title or len(title) < 3:
                    continue

                # Try to find date in cells
                date_str = None
                for cell in cells:
                    text = cell.get_text(strip=True)
                    parsed = self._parse_date_text(text)
                    if parsed:
                        date_str = parsed
                        break

                # Image
                img = row.find("img")
                image_url = None
                if img and img.get("src"):
                    image_url = self._resolve_url(img["src"])

                articles.append({
                    "url": url,
                    "title": title,
                    "date": date_str,
                    "image_url": image_url,
                })

        # If no table found, fall back to standard extraction
        if not articles:
            return super()._extract_articles_from_soup(soup)

        return articles

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        # Accept any rshp.com URL that's not just /news/
        path = url.split("rshp.com")[-1] if "rshp.com" in url else url
        return path.rstrip("/") != "/news"


custom_scraper_registry.register(RshpScraper)
