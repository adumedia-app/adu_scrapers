# operators/custom_scrapers/shl.py
"""
Schmidt Hammer Lassen (SHL) Custom Scraper
Site: https://www.shl.dk/en/agendas-insights
Strategy: HTTP + BeautifulSoup (server-side rendered)
Dates: DD.MM.YYYY format, appear as text siblings after title links
Links: /en/agendas-insights/article-slug
Structure: No card wrappers. Each article is:
    <a href="slug"><img ...></a>        (image link)
    <a href="slug">Title text</a>       (title link)
    DD.MM.YYYY                          (date as text node)
"""

import re
from typing import List, Optional
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class ShlScraper(StudioHttpScraper):
    source_id = "shl"
    source_name = "Schmidt Hammer Lassen"
    base_url = "https://www.shl.dk"
    news_url = "https://www.shl.dk/en/agendas-insights"

    # Not used — we override _extract_articles_from_soup
    card_selector = ""
    title_selector = ""
    link_selector = ""
    date_selector = ""
    date_format = ""
    image_selector = ""

    # Article URL pattern
    _ARTICLE_URL_RE = re.compile(r"/en/agendas-insights/[^\"'\s]+")

    # Date pattern: DD.MM.YYYY
    _DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")

    def _extract_articles_from_soup(self, soup: BeautifulSoup) -> List[dict]:
        """
        Extract articles from SHL's news listing.

        No card wrappers — each article is a sequence of:
        1. <a href="/en/agendas-insights/slug"><img ...></a>  (image)
        2. <a href="/en/agendas-insights/slug">Title</a>     (title)
        3. DD.MM.YYYY text                                    (date)

        We find title links (those with text), then look for
        sibling image links and date text nearby.
        """
        articles = []
        seen_urls = set()

        # Find all links matching article URL pattern
        all_links = soup.find_all("a", href=self._ARTICLE_URL_RE)
        print(f"[{self.source_id}] Found {len(all_links)} links matching /en/agendas-insights/ pattern")

        for link in all_links:
            href = link.get("href", "")
            full_url = self._resolve_url(href)

            # Deduplicate (each article has image link + title link)
            if full_url in seen_urls:
                continue

            # Get title text — skip image-only links
            title_text = link.get_text(strip=True)
            if not title_text or len(title_text) < 3:
                continue

            # Skip Danish pages
            if "/da/" in full_url or "/agendaer-indsigter/" in full_url:
                continue

            seen_urls.add(full_url)

            # Try to find date from next sibling text
            date_str = None
            next_sib = link.next_sibling
            # Walk a few siblings looking for a date
            for _ in range(5):
                if next_sib is None:
                    break
                sib_text = str(next_sib).strip() if hasattr(next_sib, 'strip') else next_sib.get_text(strip=True) if hasattr(next_sib, 'get_text') else str(next_sib).strip()
                date_match = self._DATE_RE.search(sib_text)
                if date_match:
                    try:
                        dt = datetime.strptime(date_match.group(1), "%d.%m.%Y")
                        date_str = dt.replace(tzinfo=timezone.utc).isoformat()
                    except ValueError:
                        pass
                    break
                next_sib = next_sib.next_sibling if hasattr(next_sib, 'next_sibling') else None

            # Try to find sibling image link with the same href
            image_url = None
            parent = link.parent
            if parent:
                img_link = parent.find("a", href=href)
                if img_link and img_link != link:
                    img = img_link.find("img")
                    if img:
                        for attr in ["src", "data-src"]:
                            val = img.get(attr)
                            if val and not val.startswith("data:"):
                                image_url = self._resolve_url(val)
                                break

            articles.append({
                "url": full_url,
                "title": title_text,
                "date": date_str,
                "image_url": image_url,
            })

        print(f"[{self.source_id}] Extracted {len(articles)} unique articles")
        return articles


custom_scraper_registry.register(ShlScraper)