# operators/custom_scrapers/mecanoo.py
"""
Mecanoo Custom Scraper
Site: https://www.mecanoo.nl/News/Project-updates
Strategy: HTTP + BeautifulSoup (DotNetNuke CMS, server-side rendered)
Dates: Extracted from image filenames (e.g. "2026 03 04 Project Name.jpg")
Links: /News/ID/NNN/article-slug (sequential numeric IDs)
Structure: <article class="News artNormal"> cards with image + title inside

IMPORTANT: The listing page shows ALL articles since ~2014 (300+).
We only extract the first MAX_LISTING_ARTICLES (20) since the page
is sorted newest-first. This avoids sending 300+ URLs through the
article tracker and AI pipeline every run.
"""

import re
from typing import List, Optional
from bs4 import BeautifulSoup

from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class MecanooScraper(StudioHttpScraper):
    source_id = "mecanoo"
    source_name = "Mecanoo"
    base_url = "https://www.mecanoo.nl"
    news_url = "https://www.mecanoo.nl/News/Project-updates"

    # Not used — we override _extract_articles_from_soup
    card_selector = ""
    title_selector = ""
    link_selector = ""
    date_selector = ""
    date_format = ""
    image_selector = ""

    # Only process this many articles from the listing page.
    # The page is sorted newest-first, so 5 covers several months.
    MAX_LISTING_ARTICLES = 5

    # Article URL pattern: /News/ID/NNN/slug
    _ARTICLE_URL_RE = re.compile(r"/News/ID/\d+/")

    # Date pattern in image filenames: "2026 03 04" or "2025 12 31"
    _IMG_DATE_RE = re.compile(r"(\d{4})\s+(\d{2})\s+(\d{2})")

    def _extract_date_from_image(self, article_el) -> Optional[str]:
        """
        Try to extract a date from image filename attributes.

        Mecanoo's CMS stores images with date prefixes like:
            /Portals/www/Images/News/2026 03 04 Project Name.jpg

        These appear in data-original, data-original-src, or src attributes.

        Returns:
            ISO date string (e.g. "2026-03-04") or None
        """
        img = article_el.select_one("img")
        if not img:
            return None

        # Check all image attributes that might contain the filename
        for attr in ["data-original", "data-original-src", "src"]:
            val = img.get(attr, "")
            if not val:
                continue
            match = self._IMG_DATE_RE.search(val)
            if match:
                year, month, day = match.groups()
                return f"{year}-{month}-{day}"

        return None

    def _extract_articles_from_soup(self, soup: BeautifulSoup) -> List[dict]:
        """
        Extract articles from Mecanoo's DotNetNuke news listing.

        Each article is wrapped in: <article class="News artNormal">
        containing an image link and an h2 title link.

        We limit to MAX_LISTING_ARTICLES (20) since the page lists
        ALL articles (300+) going back years.
        """
        articles = []
        seen_urls = set()

        # Find all article cards
        cards = soup.select("article.News")
        print(f"[{self.source_id}] Found {len(cards)} article cards on page")
        print(f"[{self.source_id}] Processing first {self.MAX_LISTING_ARTICLES} (newest)")

        for card in cards[:self.MAX_LISTING_ARTICLES]:
            try:
                # --- Link: find the title link matching /News/ID/NNN/ ---
                title_link = card.select_one("h2 a[href]")
                if not title_link:
                    continue

                href = title_link.get("href", "")
                if not self._ARTICLE_URL_RE.search(href):
                    continue

                full_url = self._resolve_url(href)

                # Deduplicate
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                # --- Title ---
                title_text = title_link.get_text(strip=True)
                if not title_text or len(title_text) < 3:
                    continue

                # --- Date from image filename ---
                date_str = self._extract_date_from_image(card)

                # --- Image ---
                image_url = None
                img_link = card.select_one("div.artImage a img")
                if img_link:
                    for attr in ["data-original", "data-original-src", "src"]:
                        val = img_link.get(attr)
                        if val and not val.startswith("data:"):
                            # Skip the resized/thumbnail URLs, prefer original
                            if "/DesktopModules/" in val:
                                # This is a thumbnail URL, try data-original instead
                                continue
                            image_url = self._resolve_url(val)
                            break
                    # Fallback: use thumbnail URL if no original found
                    if not image_url:
                        for attr in ["data-original", "data-original-src", "src"]:
                            val = img_link.get(attr)
                            if val and not val.startswith("data:"):
                                image_url = self._resolve_url(val)
                                break

                articles.append({
                    "url": full_url,
                    "title": title_text,
                    "date": date_str,
                    "image_url": image_url,
                })

            except Exception as e:
                print(f"[{self.source_id}] Error parsing card: {e}")
                continue

        print(f"[{self.source_id}] Extracted {len(articles)} articles (from {len(cards)} total on page)")
        return articles


custom_scraper_registry.register(MecanooScraper)