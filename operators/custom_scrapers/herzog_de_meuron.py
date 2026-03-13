# operators/custom_scrapers/herzog_de_meuron.py
"""
Herzog & de Meuron Custom Scraper
Site: https://www.herzogdemeuron.com/news/
Strategy: HTTP + embedded JSON extraction (no Playwright needed)

The news page is WordPress-based and renders via Alpine.js (client-side),
but ALL article data is embedded in the HTML inside:
    <script id='postlist-json' type='application/json'>[...]</script>

Each JSON entry contains:
    - id: post ID
    - url: full article URL (e.g., "https://www.herzogdemeuron.com/news/hdm-wins-the-box-hannover/")
    - title: article title (may contain HTML entities like &nbsp; &rsquo;)
    - subtitle: date string like "24 February 2026" (sometimes empty or German)
    - objectTermsSlugs: category slugs like ["2026", "project-updates", "awards"]
    - teaser_html: full card HTML (contains image srcsets)
    - hasImages: boolean

Date format: "DD Month YYYY" (English) — e.g., "24 February 2026"
Some older entries have German dates ("30. Oktober 2019") — handled gracefully.

Notes:
    - Major Swiss practice (Pritzker Prize winners). Very active news feed.
    - News types include: project-updates, awards, events, exhibitions, lectures,
      special-project, media
    - This site was originally classified as "Hard (Playwright)" but the embedded
      JSON makes it trivial with plain HTTP.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import List, Optional
from html import unescape

from bs4 import BeautifulSoup, Tag

from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class HerzogDeMeuronScraper(StudioHttpScraper):
    source_id = "herzog_de_meuron"
    source_name = "Herzog & de Meuron"
    base_url = "https://www.herzogdemeuron.com"
    news_url = "https://www.herzogdemeuron.com/news/"

    MAX_NEW_ARTICLES = 10

    # Not used (we override fetch_articles), but needed by base class
    card_selector = "article"
    title_selector = "h2"
    link_selector = "a"
    date_format = "%d %B %Y"

    excluded_patterns = [
        "/news/$",
        "/news$",
    ]

    async def fetch_articles(self, hours: int = 24) -> list[dict]:
        """
        Fetch new articles by extracting embedded JSON from the news page HTML.

        Instead of parsing HTML cards or calling a REST API, we extract the
        pre-rendered JSON from <script id='postlist-json'>.
        """
        print(f"[{self.source_id}] Starting fetch via embedded JSON...")
        await self._ensure_tracker()
        assert self.tracker is not None

        try:
            # Step 1: Fetch the news page HTML
            html = await self._fetch_html(self.news_url)
            if not html:
                print(f"[{self.source_id}] Failed to fetch news page")
                return []

            # Step 2: Extract JSON from <script id='postlist-json'>
            articles = self._extract_json_from_html(html)
            if not articles:
                print(f"[{self.source_id}] No articles found in embedded JSON")
                return []

            # Step 3: Check article tracker for new URLs
            all_urls = [a["url"] for a in articles]
            new_urls = await self.tracker.filter_new_articles(self.source_id, all_urls)

            print(f"[{self.source_id}] Database check:")
            print(f"   Total from page: {len(articles)}")
            print(f"   Already seen: {len(articles) - len(new_urls)}")
            print(f"   New articles: {len(new_urls)}")

            # Step 4: Mark ALL urls as seen
            await self.tracker.mark_as_seen(self.source_id, all_urls)

            if not new_urls:
                print(f"[{self.source_id}] No new articles to process")
                return []

            # Step 5: Build article dicts for new URLs
            url_to_data = {a["url"]: a for a in articles}
            new_articles = []

            for url in new_urls[:self.MAX_NEW_ARTICLES]:
                data = url_to_data.get(url, {})
                article = self._create_minimal_article_dict(
                    title=data.get("title", ""),
                    link=url,
                    published=data.get("date"),
                    image_url=data.get("image_url"),
                )
                if self._validate_article(article):
                    new_articles.append(article)
                    print(f"[{self.source_id}]    Added: {data.get('title', '')[:60]}...")

            print(f"\n[{self.source_id}] Processing Summary:")
            print(f"   Articles on page: {len(articles)}")
            print(f"   New articles: {len(new_urls)}")
            print(f"   Returning to pipeline: {len(new_articles)}")

            return new_articles

        except Exception as e:
            print(f"[{self.source_id}] Error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _extract_json_from_html(self, html: str) -> List[dict]:
        """
        Extract article list from <script id='postlist-json'> in the page HTML.

        Returns list of dicts with keys: url, title, date, image_url
        """
        soup = BeautifulSoup(html, "html.parser")
        script_tag = soup.find("script", {"id": "postlist-json"})

        if not script_tag or not isinstance(script_tag, Tag) or not script_tag.string:
            print(f"[{self.source_id}] Could not find postlist-json script tag")
            return []

        try:
            raw_data = json.loads(script_tag.string)
        except json.JSONDecodeError as e:
            print(f"[{self.source_id}] Failed to parse JSON: {e}")
            return []

        if not isinstance(raw_data, list):
            print(f"[{self.source_id}] Unexpected JSON format: {type(raw_data)}")
            return []

        articles = []
        for item in raw_data:
            try:
                url = item.get("url", "")
                if not url:
                    continue

                # Title — decode HTML entities (&nbsp; &rsquo; &amp; etc.)
                title_raw = item.get("title", "")
                title = unescape(title_raw).replace("\xa0", " ").strip()

                # Skip hidden items
                if item.get("hideInOverview", False):
                    continue

                # Date — from subtitle field (e.g., "24 February 2026")
                date_iso = self._parse_hdm_date(item.get("subtitle", ""))

                # Image — extract from teaser_html if available
                image_url = self._extract_image_from_teaser(
                    item.get("teaser_html", "")
                )

                articles.append({
                    "url": url,
                    "title": title,
                    "date": date_iso,
                    "image_url": image_url,
                })

            except Exception as e:
                print(f"[{self.source_id}] Error parsing item: {e}")
                continue

        print(f"[{self.source_id}] Extracted {len(articles)} articles from embedded JSON")
        return articles

    def _parse_hdm_date(self, date_text: str) -> Optional[str]:
        """
        Parse date from H&dM subtitle field.

        Common formats:
            "24 February 2026"   -> %d %B %Y
            "09 February 2024"   -> %d %B %Y
            "7 September 2022"   -> %d %B %Y
            "30. Oktober 2019"   -> German (handled separately)
            ""                   -> None (some entries have no date)
        """
        if not date_text or not date_text.strip():
            return None

        text = date_text.strip()

        # Remove trailing/leading dots that appear in some German entries
        text = text.replace(". ", " ").strip()

        # Try English format first (most entries)
        for fmt in ["%d %B %Y", "%d %B, %Y", "%B %d, %Y"]:
            try:
                dt = datetime.strptime(text, fmt)
                return dt.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                continue

        # Try German month names
        german_months = {
            "Januar": "January", "Februar": "February", "März": "March",
            "April": "April", "Mai": "May", "Juni": "June",
            "Juli": "July", "August": "August", "September": "September",
            "Oktober": "October", "November": "November", "Dezember": "December",
        }
        for de, en in german_months.items():
            if de in text:
                text = text.replace(de, en)
                break
        try:
            dt = datetime.strptime(text, "%d %B %Y")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass

        # Could not parse — not a problem, pipeline handles None dates
        return None

    def _extract_image_from_teaser(self, teaser_html: str) -> Optional[str]:
        """
        Extract the best image URL from the teaser_html field.

        Images are in data-srcset attributes with multiple sizes.
        We pick the largest one (last in srcset, typically 2300w).
        """
        if not teaser_html:
            return None

        try:
            soup = BeautifulSoup(teaser_html, "html.parser")
            img = soup.find("img", {"data-srcset": True})
            if not img or not isinstance(img, Tag):
                return None

            srcset_val = img.get("data-srcset", "")
            if not srcset_val:
                return None

            # .get() can return a list for multi-value attrs — normalize to str
            srcset = srcset_val if isinstance(srcset_val, str) else ",".join(srcset_val)

            # Parse srcset — entries like "url 1600w, url 1000w, ..."
            # Pick the largest (last entry, or parse widths)
            entries = [e.strip() for e in srcset.split(",") if e.strip()]
            if not entries:
                return None

            best_url = None
            best_width = 0

            for entry in entries:
                parts = entry.strip().split()
                if len(parts) >= 2:
                    url = parts[0]
                    width_str = parts[1].replace("w", "")
                    try:
                        width = int(width_str)
                        if width > best_width:
                            best_width = width
                            best_url = url
                    except ValueError:
                        continue
                elif len(parts) == 1:
                    best_url = parts[0]

            return best_url

        except Exception:
            return None

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        return "/news/" in url and url.rstrip("/") != self.news_url.rstrip("/")


custom_scraper_registry.register(HerzogDeMeuronScraper)