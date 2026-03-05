# operators/custom_scrapers/archello.py
"""
Archello Custom Scraper - HTTP Pattern Approach
Scrapes architecture projects from Archello (global architecture platform)

Site: https://archello.com/projects
Strategy: Extract links matching /projects/article-slug pattern from the projects page

Pattern Analysis:
- Article URLs: /projects/article-slug (e.g., /projects/studio-xyz-house-amsterdam)
- Non-article URLs: /projects/ (listing page itself), /news/..., /firms/..., /products/... etc.

Architecture:
- Custom scraper discovers article URLs from /projects page (no individual article visits)
- Article tracker handles new/seen filtering
- Main pipeline handles: content scraping, hero image extraction (og:image), AI filtering

On first run: All found articles marked as seen
On subsequent runs: Only new articles returned for processing

Usage:
    scraper = ArchelloScraper()
    articles = await scraper.fetch_articles()
    await scraper.close()
"""

import asyncio
import re
from typing import Optional, List, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from operators.custom_scraper_base import BaseCustomScraper, custom_scraper_registry
from storage.article_tracker import ArticleTracker


class ArchelloScraper(BaseCustomScraper):
    """
    HTTP pattern-based custom scraper for Archello.
    Extracts article URLs matching /projects/article-slug pattern from the projects page.
    """

    source_id = "archello"
    source_name = "Archello"
    base_url = "https://archello.com"

    # Configuration
    MAX_NEW_ARTICLES = 10
    PROJECTS_PAGE_URL = "https://archello.com/projects"

    # URL pattern for articles: /projects/article-slug
    # Must be /projects/ followed by a slug (letters, numbers, hyphens) — no sub-paths
    ARTICLE_PATTERN = re.compile(r'^/projects/[a-z0-9][a-z0-9-]+$', re.IGNORECASE)

    # URL patterns to EXCLUDE (not articles — these are listing/category pages)
    EXCLUDED_PATTERNS = [
        '/projects/category/',
        '/projects/type/',
        '/projects/page/',
        '/projects/tag/',
        '/news/',
        '/firms/',
        '/products/',
        '/manufacturers/',
        '/podcast',
        '/awards',
        '/about',
        '/membership',
        '#',
        'javascript:',
    ]

    def __init__(self):
        """Initialize scraper with article tracker."""
        super().__init__()
        self.tracker: Optional[ArticleTracker] = None

    async def _ensure_tracker(self):
        """Ensure article tracker is connected."""
        if not self.tracker:
            self.tracker = ArticleTracker()
            await self.tracker.connect()

    def _is_valid_article_url(self, path: str) -> bool:
        """
        Check if URL path is a valid article URL.

        Valid articles match: /projects/article-slug (no sub-paths)

        Args:
            path: URL path to check

        Returns:
            True if valid article URL
        """
        path_lower = path.lower()

        # Check excluded patterns first
        for pattern in self.EXCLUDED_PATTERNS:
            if pattern in path_lower:
                return False

        # Must match article pattern exactly
        if not self.ARTICLE_PATTERN.match(path):
            return False

        return True

    def _extract_articles_from_html(self, html: str) -> List[Tuple[str, str]]:
        """
        Extract article URLs and titles from page HTML with deduplication.

        Args:
            html: Page HTML content

        Returns:
            List of tuples: (url, title) - deduplicated
        """
        soup = BeautifulSoup(html, 'html.parser')
        seen_urls: set[str] = set()
        articles: List[Tuple[str, str]] = []

        # Find all links on the page
        all_links = soup.find_all('a', href=True)

        for link in all_links:
            href = link.get('href', '')

            # Handle relative URLs (e.g. /news/article-slug)
            if href.startswith('/'):
                path = href
            # Handle full domain URLs
            elif 'archello.com' in href:
                parsed = urlparse(href)
                path = parsed.path
            else:
                continue

            # Strip query params and fragments
            path = path.split('?')[0].split('#')[0].rstrip('/')

            # Filter: must be a valid article URL
            if not self._is_valid_article_url(path):
                continue

            # Build full URL
            full_url = f"https://archello.com{path}"

            # Deduplication: skip if already seen
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # Extract title from link text
            title = link.get_text(strip=True)

            # If title is empty or too short, try parent elements
            if not title or len(title) < 5:
                parent = link.find_parent(['article', 'div', 'li', 'section'])
                if parent:
                    heading = parent.find(['h1', 'h2', 'h3', 'h4'])
                    if heading:
                        title = heading.get_text(strip=True)

            # Last fallback: use slug from URL
            if not title or len(title) < 3:
                slug = path.split('/')[-1]
                title = slug.replace('-', ' ').title()

            # Clean title
            title = ' '.join(title.split())[:200]

            if title:
                articles.append((full_url, title))

        return articles

    async def fetch_articles(self, hours: int = 24) -> list[dict]:
        """
        Fetch new articles from Archello.

        Workflow:
        1. Load Archello /projects page
        2. Extract all article links matching /projects/article-slug (with deduplication)
        3. Check database for new URLs
        4. Mark all found URLs as seen
        5. Return minimal article dicts for new URLs only
        6. Main pipeline handles: content, hero image (og:image), dates

        Args:
            hours: Ignored (we use database tracking instead of timestamps)

        Returns:
            List of minimal article dicts
        """
        print(f"[{self.source_id}] Starting HTTP pattern scraping...")

        await self._ensure_tracker()

        try:
            page = await self._create_page()

            try:
                # ============================================================
                # Step 1: Load Projects Page
                # ============================================================
                print(f"[{self.source_id}] Loading projects page: {self.PROJECTS_PAGE_URL}")
                await page.goto(self.PROJECTS_PAGE_URL, timeout=self.timeout, wait_until="networkidle")
                await page.wait_for_timeout(2000)  # Allow JS content to settle

                html = await page.content()

                # ============================================================
                # Step 2: Extract Article Links (with deduplication)
                # ============================================================
                extracted = self._extract_articles_from_html(html)
                print(f"[{self.source_id}] Found {len(extracted)} unique article links")

                if not extracted:
                    print(f"[{self.source_id}] No articles found — check /projects URL patterns")
                    return []

                # ============================================================
                # Step 3: Check Database for New URLs
                # ============================================================
                if not self.tracker:
                    raise RuntimeError("Article tracker not initialized")

                all_urls = [url for url, _ in extracted]

                new_urls = await self.tracker.filter_new_articles(self.source_id, all_urls)

                url_to_title = {url: title for url, title in extracted}

                print(f"[{self.source_id}] Database check:")
                print(f"   Total extracted: {len(extracted)}")
                print(f"   Already seen: {len(extracted) - len(new_urls)}")
                print(f"   New articles: {len(new_urls)}")

                # ============================================================
                # Step 4: Mark All URLs as Seen
                # ============================================================
                await self.tracker.mark_as_seen(self.source_id, all_urls)

                if not new_urls:
                    print(f"[{self.source_id}] No new articles to process")
                    return []

                # ============================================================
                # Step 5: Create Minimal Article Dicts
                # ============================================================
                new_articles: list[dict] = []

                for url in new_urls[:self.MAX_NEW_ARTICLES]:
                    title = url_to_title.get(url, url.split('/')[-1].replace('-', ' ').title())

                    # Create minimal article dict
                    # Main pipeline fills in: content, hero image, date
                    article = self._create_minimal_article_dict(
                        title=title,
                        link=url,
                        published=None  # Extracted by main pipeline
                    )

                    if self._validate_article(article):
                        new_articles.append(article)
                        print(f"[{self.source_id}]    Added: {title[:50]}...")

                # Summary
                print(f"\n[{self.source_id}] Processing Summary:")
                print(f"   Articles found: {len(extracted)}")
                print(f"   New articles: {len(new_urls)}")
                print(f"   Returning to pipeline: {len(new_articles)}")

                return new_articles

            finally:
                await page.close()

        except Exception as e:
            print(f"[{self.source_id}] Error in scraping: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def close(self):
        """Close browser and tracker connections."""
        await super().close()

        if self.tracker:
            await self.tracker.close()
            self.tracker = None


# Register this scraper
custom_scraper_registry.register(ArchelloScraper)


# =============================================================================
# Standalone Test
# =============================================================================

async def test_archello_scraper():
    """Test the Archello HTTP pattern scraper."""
    print("=" * 60)
    print("Testing Archello Custom Scraper")
    print("=" * 60)

    from storage.article_tracker import ArticleTracker
    print(f"\nTEST_MODE: {ArticleTracker.TEST_MODE}")
    if ArticleTracker.TEST_MODE:
        print("   All articles will appear as 'new' (ignoring database)")
    else:
        print("   Normal mode - filtering seen articles")

    scraper = ArchelloScraper()

    try:
        # Test connection
        print("\n1. Testing connection...")
        connected = await scraper.test_connection()
        if not connected:
            print("   Connection failed")
            return

        # Tracker stats
        print("\n2. Checking tracker stats...")
        await scraper._ensure_tracker()
        if scraper.tracker:
            stats = await scraper.tracker.get_stats(source_id="archello")
            print(f"   Total articles in database: {stats['total_articles']}")

        # Fetch articles
        print("\n3. Running scraping...")
        articles = await scraper.fetch_articles(hours=24)

        print(f"\n   Found {len(articles)} NEW articles")

        if articles:
            print("\n4. New articles:")
            for i, article in enumerate(articles, 1):
                print(f"\n   --- Article {i} ---")
                print(f"   Title: {article['title'][:60]}")
                print(f"   Link: {article['link']}")
        else:
            print("\n4. No new articles (all previously seen)")

        print("\n" + "=" * 60)
        print("Test complete!")
        print("=" * 60)

    finally:
        await scraper.close()


if __name__ == "__main__":
    asyncio.run(test_archello_scraper())