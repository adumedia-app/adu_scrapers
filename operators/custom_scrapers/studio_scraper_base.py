# operators/custom_scrapers/studio_scraper_base.py
"""
Lightweight HTTP Scraper Base for Architecture Studio News Pages

Uses aiohttp + BeautifulSoup instead of Playwright for server-side rendered sites.
Faster, cheaper, and more reliable than headless browser for simple HTML pages.

Design:
    - Subclasses define CSS selectors and date format as class attributes
    - Base handles: HTTP fetch, HTML parsing, article tracking, deduplication
    - Each new studio scraper = ~30 lines of configuration

Usage:
    class BigScraper(StudioHttpScraper):
        source_id = "big"
        source_name = "BIG"
        base_url = "https://big.dk"
        news_url = "https://big.dk/news"
        card_selector = "article.news-card"
        title_selector = "h2"
        link_selector = "a"
        date_selector = ".date"
        date_format = "%d.%m.%Y"
"""

import asyncio
import re
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
from urllib.parse import urljoin, urlparse
from html import unescape

import aiohttp
from bs4 import BeautifulSoup, Tag

from operators.custom_scraper_base import BaseCustomScraper, custom_scraper_registry
from storage.article_tracker import ArticleTracker


class StudioHttpScraper(BaseCustomScraper):
    """
    Lightweight HTTP scraper base for architecture studio news pages.

    Subclasses MUST define:
        source_id: str          - Unique ID (e.g., "big")
        source_name: str        - Display name (e.g., "BIG")
        base_url: str           - Site root (e.g., "https://big.dk")
        news_url: str           - News listing page URL

    Subclasses SHOULD define:
        card_selector: str      - CSS selector for article cards
        title_selector: str     - CSS selector for title within card
        link_selector: str      - CSS selector for link within card (or on card itself)
        date_selector: str      - CSS selector for date within card (optional)
        date_format: str        - strptime format for dates (optional)
        image_selector: str     - CSS selector for image within card (optional)
        category_selector: str  - CSS selector for category label (optional)
        allowed_categories: list - Only process cards with these categories (optional)

    Subclasses MAY override:
        _extract_articles_from_soup() - For non-standard HTML structures
        _parse_date_text()            - For unusual date formats
        _is_valid_article_url()       - For custom URL filtering
    """

    # --- REQUIRED (subclass must define) ---
    news_url: str = ""

    # --- SELECTORS (subclass should define) ---
    card_selector: str = "article"
    title_selector: str = "h2"
    link_selector: str = "a"
    date_selector: str = ""          # Empty = no date on listing page
    date_format: str = ""            # strptime format, e.g. "%d.%m.%Y"
    image_selector: str = "img"
    category_selector: str = ""      # Empty = no category filtering
    allowed_categories: list = []    # Empty = accept all categories

    # --- CONFIGURATION ---
    MAX_NEW_ARTICLES: int = 10

    # URL patterns to always exclude
    GLOBAL_EXCLUDED_PATTERNS = [
        '#', 'javascript:', 'mailto:', 'tel:',
        '/page/', '/search/', '/tag/', '/category/',
        '/author/', '/login/', '/register/',
    ]

    # Additional excluded patterns (subclass can extend)
    excluded_patterns: list = []

    def __init__(self):
        """Initialize scraper with article tracker."""
        super().__init__()
        self.tracker: Optional[ArticleTracker] = None

    async def _ensure_tracker(self):
        """Ensure article tracker is connected."""
        if not self.tracker:
            self.tracker = ArticleTracker()
            await self.tracker.connect()

    # =========================================================================
    # HTTP Fetching (replaces Playwright for server-rendered sites)
    # =========================================================================

    async def _fetch_html(self, url: str) -> Optional[str]:
        """
        Fetch page HTML using aiohttp (no browser needed).

        Args:
            url: Page URL to fetch

        Returns:
            HTML string or None if failed
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers, ssl=False) as response:
                    if response.status == 200:
                        html = await response.text()
                        print(f"[{self.source_id}] Fetched {url} ({len(html)} bytes)")
                        return html
                    else:
                        print(f"[{self.source_id}] HTTP {response.status} from {url}")
                        return None
        except Exception as e:
            print(f"[{self.source_id}] Fetch error: {e}")
            return None

    # =========================================================================
    # HTML Parsing
    # =========================================================================

    def _extract_articles_from_soup(self, soup: BeautifulSoup) -> List[dict]:
        """
        Extract articles from parsed HTML.

        Override this method for non-standard HTML structures.

        Args:
            soup: Parsed BeautifulSoup object

        Returns:
            List of dicts with keys: url, title, date (optional), image_url (optional)
        """
        articles = []
        seen_urls = set()

        cards = soup.select(self.card_selector)
        print(f"[{self.source_id}] Found {len(cards)} cards with selector '{self.card_selector}'")

        for card in cards:
            try:
                # --- Category filter ---
                if self.category_selector and self.allowed_categories:
                    cat_el = card.select_one(self.category_selector)
                    if cat_el:
                        cat_text = cat_el.get_text(strip=True).lower()
                        if not any(c.lower() in cat_text for c in self.allowed_categories):
                            continue

                # --- Link ---
                link_url = self._extract_link(card)
                if not link_url:
                    continue

                # Resolve to absolute URL
                full_url = self._resolve_url(link_url)

                # Validate and deduplicate
                if not self._is_valid_article_url(full_url):
                    continue
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                # --- Title ---
                title = self._extract_title(card)
                if not title or len(title) < 3:
                    continue

                # --- Date (optional) ---
                date_str = self._extract_date(card)

                # --- Image (optional) ---
                image_url = self._extract_image(card)

                articles.append({
                    "url": full_url,
                    "title": title,
                    "date": date_str,
                    "image_url": image_url,
                })

            except Exception as e:
                print(f"[{self.source_id}] Error parsing card: {e}")
                continue

        return articles

    def _extract_link(self, card: Tag) -> Optional[str]:
        """Extract article link from card."""
        # First try the link_selector within card
        if self.link_selector:
            link_el = card.select_one(self.link_selector)
            if link_el and link_el.get("href"):
                return link_el["href"]

        # If card itself is a link
        if card.name == "a" and card.get("href"):
            return card["href"]

        # Try any <a> within card
        a_tag = card.find("a", href=True)
        if a_tag:
            return a_tag["href"]

        return None

    def _extract_title(self, card: Tag) -> str:
        """Extract article title from card."""
        if self.title_selector:
            title_el = card.select_one(self.title_selector)
            if title_el:
                return self._clean_text(title_el.get_text(strip=True))

        # Fallback: try heading tags
        for tag in ["h1", "h2", "h3", "h4"]:
            heading = card.find(tag)
            if heading:
                return self._clean_text(heading.get_text(strip=True))

        # Fallback: link text
        a_tag = card.find("a")
        if a_tag:
            return self._clean_text(a_tag.get_text(strip=True))

        return ""

    def _extract_date(self, card: Tag) -> Optional[str]:
        """Extract and parse date from card. Returns ISO format string or None."""
        if not self.date_selector:
            return None

        date_el = card.select_one(self.date_selector)
        if not date_el:
            return None

        date_text = date_el.get_text(strip=True)
        return self._parse_date_text(date_text)

    def _parse_date_text(self, text: str) -> Optional[str]:
        """
        Parse date text into ISO format string.

        Override for unusual date formats.

        Args:
            text: Raw date text from page

        Returns:
            ISO format datetime string or None
        """
        if not text:
            return None

        # Try the configured format first
        if self.date_format:
            try:
                dt = datetime.strptime(text.strip(), self.date_format)
                return dt.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass

        # Try common date formats as fallback
        common_formats = [
            "%d.%m.%Y",          # 06.03.2026
            "%d.%m.%y",          # 06.03.26
            "%B %d, %Y",         # March 06, 2026
            "%b %d, %Y",         # Mar 06, 2026
            "%d %B %Y",          # 06 March 2026
            "%d %b %Y",          # 06 Mar 2026
            "%Y-%m-%d",          # 2026-03-06
            "%m.%d.%Y",          # 03.06.2026
            "%d-%m-%Y",          # 06-03-2026
            "%B %d %Y",          # March 06 2026 (no comma)
            "%d/%m/%Y",          # 06/03/2026
            "%m/%d/%Y",          # 03/06/2026
            "%b. %d, %Y",        # Mar. 06, 2026
            "%B %Y",             # March 2026
            "%d %B, %Y",         # 06 March, 2026
            "%d.%m",             # 06.03 (no year, assume current)
        ]

        text_clean = text.strip()

        for fmt in common_formats:
            try:
                dt = datetime.strptime(text_clean, fmt)
                # If no year in format, use current year
                if "%Y" not in fmt and "%y" not in fmt:
                    dt = dt.replace(year=datetime.now().year)
                return dt.replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                continue

        print(f"[{self.source_id}] Could not parse date: '{text}'")
        return None

    def _extract_image(self, card: Tag) -> Optional[str]:
        """Extract image URL from card."""
        if not self.image_selector:
            return None

        img_el = card.select_one(self.image_selector)
        if not img_el:
            return None

        # Try common image attributes
        for attr in ["src", "data-src", "data-lazy-src", "srcset"]:
            val = img_el.get(attr)
            if val:
                # For srcset, take first URL
                if attr == "srcset":
                    val = val.split(",")[0].strip().split(" ")[0]
                # Skip base64 placeholders and SVGs
                if val.startswith("data:") or val.endswith(".svg"):
                    continue
                return self._resolve_url(val)

        return None

    def _is_valid_article_url(self, url: str) -> bool:
        """
        Check if URL is a valid article (not a category page, etc.).

        Override for custom URL validation.
        """
        url_lower = url.lower()

        # Check global excluded patterns
        for pattern in self.GLOBAL_EXCLUDED_PATTERNS:
            if pattern in url_lower:
                return False

        # Check source-specific excluded patterns
        for pattern in self.excluded_patterns:
            if pattern in url_lower:
                return False

        # Must be a URL on the same domain
        try:
            parsed_base = urlparse(self.base_url)
            parsed_url = urlparse(url)
            if parsed_url.netloc and parsed_url.netloc != parsed_base.netloc:
                # Allow www variant
                base_domain = parsed_base.netloc.replace("www.", "")
                url_domain = parsed_url.netloc.replace("www.", "")
                if base_domain != url_domain:
                    return False
        except Exception:
            pass

        return True

    # =========================================================================
    # Main Fetch Method
    # =========================================================================

    async def fetch_articles(self, hours: int = 24) -> list[dict]:
        """
        Fetch new articles from studio news page.

        Workflow:
        1. Fetch news page HTML via HTTP
        2. Parse article cards with BeautifulSoup
        3. Check article tracker for new URLs
        4. Return minimal article dicts for pipeline processing

        Args:
            hours: Ignored (uses database tracking instead)

        Returns:
            List of minimal article dicts
        """
        print(f"[{self.source_id}] Starting HTTP scraping...")
        await self._ensure_tracker()

        try:
            # Step 1: Fetch HTML
            url = self.news_url or self.base_url
            html = await self._fetch_html(url)
            if not html:
                print(f"[{self.source_id}] Failed to fetch HTML")
                return []

            # Step 2: Parse articles
            soup = BeautifulSoup(html, "html.parser")
            extracted = self._extract_articles_from_soup(soup)
            print(f"[{self.source_id}] Extracted {len(extracted)} articles")

            if not extracted:
                return []

            # Step 3: Check article tracker for new URLs
            all_urls = [a["url"] for a in extracted]
            new_urls = await self.tracker.filter_new_articles(self.source_id, all_urls)

            print(f"[{self.source_id}] Database check:")
            print(f"   Total extracted: {len(extracted)}")
            print(f"   Already seen: {len(extracted) - len(new_urls)}")
            print(f"   New articles: {len(new_urls)}")

            # Step 4: Mark ALL urls as seen (before any early returns)
            await self.tracker.mark_as_seen(self.source_id, all_urls)

            if not new_urls:
                print(f"[{self.source_id}] No new articles to process")
                return []

            # Step 5: Build article dicts for new URLs
            url_to_data = {a["url"]: a for a in extracted}
            new_articles = []

            for url in new_urls[:self.MAX_NEW_ARTICLES]:
                data = url_to_data.get(url, {})
                article = self._create_minimal_article_dict(
                    title=data.get("title", ""),
                    link=url,
                    published=data.get("date"),  # May be None
                )

                if self._validate_article(article):
                    new_articles.append(article)
                    print(f"[{self.source_id}]    Added: {data.get('title', '')[:60]}...")

            print(f"\n[{self.source_id}] Processing Summary:")
            print(f"   Articles found: {len(extracted)}")
            print(f"   New articles: {len(new_urls)}")
            print(f"   Returning to pipeline: {len(new_articles)}")

            return new_articles

        except Exception as e:
            print(f"[{self.source_id}] Error: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def close(self):
        """Close tracker connection. No browser to close for HTTP scrapers."""
        if self.tracker:
            await self.tracker.close()
            self.tracker = None
        print(f"[{self.source_id}] Scraper closed")
