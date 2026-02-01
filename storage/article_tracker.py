# storage/article_tracker.py
"""
Article Tracker - Supabase Database for Custom Scrapers

Tracks seen article URLs to prevent reprocessing.
Simple URL-based tracking: store URLs when discovered, filter against them next run.

Database Schema:
    - scraped_articles table: stores seen URLs per source
    - Unique constraint on (source_id, url) for fast lookups

Usage:
    tracker = ArticleTracker()
    await tracker.connect()

    # URL tracking workflow  
    new_urls = await tracker.filter_new_articles(source_id, url_list)
    await tracker.mark_as_seen(source_id, url_list)
"""

import os
from typing import Optional, List
from datetime import datetime

# Import Supabase client
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None


class ArticleTracker:
    """Supabase-based article URL tracking for custom scrapers."""

    # ========================================
    # TEST MODE - Set to True to ignore "seen" status
    # This makes all articles appear as "new" for testing
    # Set via environment variable: SCRAPER_TEST_MODE=true
    # ========================================
    TEST_MODE = os.getenv("SCRAPER_TEST_MODE", "").lower() == "true"

    def __init__(self):
        """Initialize article tracker with Supabase credentials from environment."""
        if not SUPABASE_AVAILABLE:
            raise ImportError("Supabase package not installed. Run: pip install supabase")

        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")

        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables must be set")

        self.client: Optional[Client] = None

    async def connect(self):
        """Connect to Supabase."""
        if self.client:
            return

        try:
            self.client = create_client(self.supabase_url, self.supabase_key)

            # Test connection by attempting a simple query
            self.client.table("scraped_articles").select("id").limit(1).execute()

            # Show mode status
            if self.TEST_MODE:
                print("⚠️  Article tracker TEST MODE ENABLED - all articles will appear as 'new'")

            print("✅ Article tracker connected to Supabase")

        except Exception as e:
            raise RuntimeError(f"Failed to connect to Supabase: {e}")

    # =========================================================================
    # URL Tracking - Core Methods
    # =========================================================================

    async def filter_new_articles(self, source_id: str, urls: List[str]) -> List[str]:
        """
        Filter list of URLs to only those not seen before.

        This is the main method for detecting new articles.
        Respects TEST_MODE: when enabled, returns all URLs as "new".

        Args:
            source_id: Source identifier (e.g., 'bauwelt')
            urls: List of article URLs found on homepage

        Returns:
            List of URLs not previously seen (new articles)
        """
        if not self.client:
            raise RuntimeError("Not connected to Supabase")

        if not urls:
            return []

        # TEST MODE: Return all URLs as "new" for testing
        if self.TEST_MODE:
            print(f"   ⚠️  TEST MODE: Returning ALL {len(urls)} URLs as 'new'")
            return urls

        try:
            # Query Supabase for existing URLs
            response = self.client.table("scraped_articles")\
                .select("url")\
                .eq("source_id", source_id)\
                .in_("url", urls)\
                .execute()

            # Get set of seen URLs
            seen_urls = set(row["url"] for row in response.data)

            # Return URLs not in database
            new_urls = [url for url in urls if url not in seen_urls]

            print(f"   Database: {len(seen_urls)} seen, {len(new_urls)} new")

            return new_urls

        except Exception as e:
            print(f"   ⚠️  Error filtering URLs: {e}")
            # On error, return all URLs as "new" to be safe
            return urls

    async def mark_as_seen(self, source_id: str, urls: List[str]) -> int:
        """
        Mark URLs as seen in the database.

        Call this after discovering URLs on homepage to track them
        for future runs.

        Args:
            source_id: Source identifier
            urls: List of article URLs to mark as seen

        Returns:
            Number of URLs marked as seen
        """
        if not self.client:
            raise RuntimeError("Not connected to Supabase")

        if not urls:
            return 0

        marked = 0
        current_time = datetime.utcnow().isoformat()

        for url in urls:
            try:
                # Try to insert new record
                # If URL already exists, update last_checked timestamp
                self.client.table("scraped_articles").upsert({
                    "source_id": source_id,
                    "url": url,
                    "last_checked": current_time
                }, on_conflict="source_id,url").execute()

                marked += 1

            except Exception as e:
                print(f"   ⚠️  Error marking URL as seen: {e}")
                continue

        print(f"   Marked {marked} URLs as seen in database")
        return marked

    async def is_seen(self, source_id: str, url: str) -> bool:
        """
        Check if a single URL has been seen before.

        Args:
            source_id: Source identifier
            url: Article URL to check

        Returns:
            True if URL exists in database
        """
        if not self.client:
            raise RuntimeError("Not connected to Supabase")

        # TEST MODE: Always return False (not seen)
        if self.TEST_MODE:
            return False

        try:
            response = self.client.table("scraped_articles")\
                .select("id")\
                .eq("source_id", source_id)\
                .eq("url", url)\
                .limit(1)\
                .execute()

            return len(response.data) > 0

        except Exception as e:
            print(f"   ⚠️  Error checking URL: {e}")
            return False

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_stats(self, source_id: Optional[str] = None) -> dict:
        """
        Get statistics about tracked articles.

        Args:
            source_id: Optional source to filter by (None = all sources)

        Returns:
            Dict with statistics
        """
        if not self.client:
            raise RuntimeError("Not connected to Supabase")

        try:
            if source_id:
                # Count for specific source
                count_response = self.client.table("scraped_articles")\
                    .select("id", count="exact")\
                    .eq("source_id", source_id)\
                    .execute()

                count = count_response.count if hasattr(count_response, 'count') else len(count_response.data)

                # Get oldest and newest
                oldest_response = self.client.table("scraped_articles")\
                    .select("first_seen")\
                    .eq("source_id", source_id)\
                    .order("first_seen", desc=False)\
                    .limit(1)\
                    .execute()

                newest_response = self.client.table("scraped_articles")\
                    .select("first_seen")\
                    .eq("source_id", source_id)\
                    .order("first_seen", desc=True)\
                    .limit(1)\
                    .execute()

                oldest = oldest_response.data[0]["first_seen"] if oldest_response.data else None
                newest = newest_response.data[0]["first_seen"] if newest_response.data else None

            else:
                # Count all articles
                count_response = self.client.table("scraped_articles")\
                    .select("id", count="exact")\
                    .execute()

                count = count_response.count if hasattr(count_response, 'count') else len(count_response.data)

                # Get oldest and newest
                oldest_response = self.client.table("scraped_articles")\
                    .select("first_seen")\
                    .order("first_seen", desc=False)\
                    .limit(1)\
                    .execute()

                newest_response = self.client.table("scraped_articles")\
                    .select("first_seen")\
                    .order("first_seen", desc=True)\
                    .limit(1)\
                    .execute()

                oldest = oldest_response.data[0]["first_seen"] if oldest_response.data else None
                newest = newest_response.data[0]["first_seen"] if newest_response.data else None

            return {
                "total_articles": count or 0,
                "oldest_seen": oldest,
                "newest_seen": newest,
            }

        except Exception as e:
            print(f"   ⚠️  Error getting stats: {e}")
            return {
                "total_articles": 0,
                "oldest_seen": None,
                "newest_seen": None,
            }

    async def get_source_counts(self) -> dict:
        """
        Get article counts per source.

        Returns:
            Dict mapping source_id to count
        """
        if not self.client:
            raise RuntimeError("Not connected to Supabase")

        try:
            # Get all articles grouped by source
            response = self.client.table("scraped_articles")\
                .select("source_id")\
                .execute()

            # Count manually since Supabase doesn't have GROUP BY in the Python client
            counts = {}
            for row in response.data:
                source_id = row["source_id"]
                counts[source_id] = counts.get(source_id, 0) + 1

            # Sort by count descending
            sorted_counts = dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
            return sorted_counts

        except Exception as e:
            print(f"   ⚠️  Error getting source counts: {e}")
            return {}

    # =========================================================================
    # Maintenance
    # =========================================================================

    async def clear_source(self, source_id: str) -> int:
        """
        Clear all tracked articles for a source.
        Useful for resetting a scraper's state.

        Args:
            source_id: Source identifier

        Returns:
            Number of articles deleted
        """
        if not self.client:
            raise RuntimeError("Not connected to Supabase")

        try:
            # First, count how many we're deleting
            count_response = self.client.table("scraped_articles")\
                .select("id", count="exact")\
                .eq("source_id", source_id)\
                .execute()

            count = count_response.count if hasattr(count_response, 'count') else len(count_response.data)

            # Delete all articles for this source
            self.client.table("scraped_articles")\
                .delete()\
                .eq("source_id", source_id)\
                .execute()

            print(f"[{source_id}] Cleared {count} tracked URLs")
            return count

        except Exception as e:
            print(f"   ⚠️  Error clearing source: {e}")
            return 0

    async def clear_all(self) -> int:
        """
        Clear ALL tracked articles (all sources).
        Use with caution!

        Returns:
            Number of articles deleted
        """
        if not self.client:
            raise RuntimeError("Not connected to Supabase")

        try:
            # First, count total
            count_response = self.client.table("scraped_articles")\
                .select("id", count="exact")\
                .execute()

            count = count_response.count if hasattr(count_response, 'count') else len(count_response.data)

            # Delete all articles
            self.client.table("scraped_articles")\
                .delete()\
                .neq("id", 0)\
                .execute()  # Delete where id != 0 (deletes all)

            print(f"⚠️  Cleared ALL {count} tracked URLs from database")
            return count

        except Exception as e:
            print(f"   ⚠️  Error clearing all: {e}")
            return 0

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def close(self):
        """Close Supabase connection (cleanup if needed)."""
        # Supabase client doesn't need explicit closing
        # But we'll set it to None for consistency
        self.client = None
        print("✅ Article tracker disconnected")