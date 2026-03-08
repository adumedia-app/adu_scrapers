# operators/custom_scrapers/som.py
"""
SOM (Skidmore, Owings & Merrill) Custom Scraper
Site: https://www.som.com/about/news/
Strategy: WordPress REST API (custom post type "news")
Article URLs: https://www.som.com/news/article-slug/

Notes:
    - WordPress site, but news listing page is JS-rendered (no articles in raw HTML)
    - Standard WP /wp-json/wp/v2/posts returns [] (empty) because SOM uses
      a custom post type called "news"
    - The correct endpoint is: /wp-json/wp/v2/news
    - Returns structured JSON with id, title, link, date, slug, etc.
    - Individual article pages ARE server-side rendered (pipeline can scrape them)
    - High posting frequency. Major global architecture/engineering firm.
    - Also has Chinese version at somchina.cn
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup

from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class SomScraper(StudioHttpScraper):
    source_id = "som"
    source_name = "SOM"
    base_url = "https://www.som.com"
    news_url = "https://www.som.com/about/news/"

    # WordPress REST API endpoint (custom post type "news")
    WP_API_URL = "https://www.som.com/wp-json/wp/v2/news"

    MAX_NEW_ARTICLES = 10

    # Not used (we override fetch_articles), but needed by base class
    card_selector = "article"
    title_selector = "h2"
    link_selector = "a"
    date_format = "%B %d, %Y"

    excluded_patterns = [
        "/about/news/$",
        "/about/news$",
    ]

    async def fetch_articles(self, hours: int = 24) -> list[dict]:
        """
        Fetch new articles via WordPress REST API.

        The standard StudioHttpScraper flow (fetch HTML -> parse cards) won't work
        because the news listing page is JS-rendered. Instead, we call the WP API
        directly, which returns structured JSON.
        """
        print(f"[{self.source_id}] Starting fetch via WP REST API...")
        await self._ensure_tracker()

        try:
            # Step 1: Fetch articles from WP API
            articles = await self._fetch_via_wp_api()

            if not articles:
                print(f"[{self.source_id}] WP API returned no articles")
                return []

            # Step 2: Check article tracker for new URLs
            all_urls = [a["url"] for a in articles]
            new_urls = await self.tracker.filter_new_articles(self.source_id, all_urls)

            print(f"[{self.source_id}] Database check:")
            print(f"   Total from API: {len(articles)}")
            print(f"   Already seen: {len(articles) - len(new_urls)}")
            print(f"   New articles: {len(new_urls)}")

            # Step 3: Mark ALL urls as seen
            await self.tracker.mark_as_seen(self.source_id, all_urls)

            if not new_urls:
                print(f"[{self.source_id}] No new articles to process")
                return []

            # Step 4: Build article dicts for new URLs
            url_to_data = {a["url"]: a for a in articles}
            new_articles = []

            for url in new_urls[:self.MAX_NEW_ARTICLES]:
                data = url_to_data.get(url, {})
                article = self._create_minimal_article_dict(
                    title=data.get("title", ""),
                    link=url,
                    published=data.get("date"),
                )
                if self._validate_article(article):
                    new_articles.append(article)
                    print(f"[{self.source_id}]    Added: {data.get('title', '')[:60]}...")

            print(f"\n[{self.source_id}] Processing Summary:")
            print(f"   Articles from API: {len(articles)}")
            print(f"   New articles: {len(new_urls)}")
            print(f"   Returning to pipeline: {len(new_articles)}")

            return new_articles

        except Exception as e:
            print(f"[{self.source_id}] Error: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def _fetch_via_wp_api(self) -> List[dict]:
        """
        Fetch articles from WordPress REST API.

        Endpoint: /wp-json/wp/v2/news
        Returns JSON array of post objects with:
            - id, title.rendered, link, date, slug, status, type
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                params = {
                    "per_page": 15,
                    "orderby": "date",
                    "order": "desc",
                }
                async with session.get(
                    self.WP_API_URL,
                    headers=headers,
                    params=params,
                    ssl=False
                ) as response:
                    if response.status != 200:
                        print(f"[{self.source_id}] WP API returned HTTP {response.status}")
                        return []

                    data = await response.json()

            if not isinstance(data, list):
                print(f"[{self.source_id}] WP API returned unexpected format: {type(data)}")
                return []

            articles = []
            for post in data:
                try:
                    # Title comes as {"rendered": "Article Title"}
                    title_obj = post.get("title", {})
                    title = title_obj.get("rendered", "") if isinstance(title_obj, dict) else str(title_obj)

                    # Strip any HTML entities/tags from title
                    if title and "<" in title:
                        title = BeautifulSoup(title, "html.parser").get_text(strip=True)

                    # Link — full URL like https://www.som.com/news/alatau-city/
                    link = post.get("link", "")

                    # Date — ISO format like "2026-03-05T13:11:58"
                    date_str = post.get("date", "")

                    if not title or not link:
                        continue

                    # Parse date
                    date_iso = None
                    if date_str:
                        try:
                            dt = datetime.fromisoformat(date_str)
                            date_iso = dt.replace(tzinfo=timezone.utc).isoformat()
                        except ValueError:
                            pass

                    articles.append({
                        "url": link,
                        "title": title,
                        "date": date_iso,
                        "image_url": None,
                    })

                except Exception as e:
                    print(f"[{self.source_id}] Error parsing post: {e}")
                    continue

            print(f"[{self.source_id}] WP API returned {len(articles)} articles")
            return articles

        except Exception as e:
            print(f"[{self.source_id}] WP API error: {e}")
            return []

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        if "som.com" not in url:
            return False
        path = url.split("som.com")[-1] if "som.com" in url else url
        clean_path = path.rstrip("/")
        skip_paths = ["/about/news", "/about", "/expertise", "/ideas",
                      "/culture", "/studios", ""]
        return clean_path not in skip_paths


custom_scraper_registry.register(SomScraper)
