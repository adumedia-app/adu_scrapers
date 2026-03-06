# operators/custom_scrapers/mecanoo.py
"""
Mecanoo Custom Scraper
Site: https://www.mecanoo.nl/News/Project-updates
Strategy: HTTP + BeautifulSoup (DotNetNuke CMS, server-side rendered)
Dates: No dates on listing page — relies on article tracker for "new" detection
Links: /News/ID/NNN/article-slug (sequential numeric IDs)
Structure: No card containers — articles are h2 > a[href*='/News/ID/'] elements
           with image links as siblings. We extract directly from h2 title links.
"""

import re
from typing import List
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

    # Article URL pattern: /News/ID/NNN/slug
    _ARTICLE_URL_RE = re.compile(r"/News/ID/\d+/")

    def _extract_articles_from_soup(self, soup: BeautifulSoup) -> List[dict]:
        """
        Extract articles from Mecanoo's DotNetNuke news listing.

        The page has no card wrappers. Each article appears as:
            <a href="/News/ID/733/slug"><img ...></a>
            <h2><a href="/News/ID/733/slug">Title text</a></h2>

        We find all h2 > a links matching /News/ID/NNN/ pattern,
        then look for a sibling image link with the same URL.
        """
        articles = []
        seen_urls = set()

        # Find all links matching the article URL pattern
        all_links = soup.find_all("a", href=self._ARTICLE_URL_RE)
        print(f"[{self.source_id}] Found {len(all_links)} links matching /News/ID/NNN/ pattern")

        for link in all_links:
            href = link.get("href", "")
            full_url = self._resolve_url(href)

            # Deduplicate (each article has 2 links: image + title)
            if full_url in seen_urls:
                continue

            # Get title text — skip image-only links (no text)
            title_text = link.get_text(strip=True)
            if not title_text or len(title_text) < 3:
                continue

            seen_urls.add(full_url)

            # Try to find the sibling image link with the same href
            image_url = None
            parent = link.parent  # likely h2
            if parent:
                prev_sibling = parent.find_previous_sibling("a", href=href)
                if prev_sibling:
                    img = prev_sibling.find("img")
                    if img:
                        for attr in ["src", "data-src"]:
                            val = img.get(attr)
                            if val and not val.startswith("data:"):
                                image_url = self._resolve_url(val)
                                break

            articles.append({
                "url": full_url,
                "title": title_text,
                "date": None,  # No dates on listing page
                "image_url": image_url,
            })

        print(f"[{self.source_id}] Extracted {len(articles)} unique articles")
        return articles


custom_scraper_registry.register(MecanooScraper)