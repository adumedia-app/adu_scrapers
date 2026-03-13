# operators/custom_scrapers/foster_and_partners.py
"""
Foster + Partners Custom Scraper
Site: https://www.fosterandpartners.com/news
Strategy: Umbraco CMS API (content.fosterandpartners.com/api/articles)

Notes:
    - Angular SSR site with Umbraco headless CMS backend
    - News listing page is JS-rendered, but the API is public and returns clean JSON
    - API endpoint: https://content.fosterandpartners.com/api/articles
    - Supports pagination via pageSize and pageIndex params
    - Each article has: title, reference (slug), date, heroImage, content (snippet)
    - Article URLs: https://www.fosterandpartners.com/news/news-article-list/{reference}/
    - Hero images: https://content.fosterandpartners.com{heroImage}
    - Very high-profile global practice — one of the world's largest architecture firms
    - ~1059 articles total in the archive
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp
from bs4 import BeautifulSoup

from operators.custom_scrapers.studio_scraper_base import StudioHttpScraper
from operators.custom_scraper_base import custom_scraper_registry


class FosterAndPartnersScraper(StudioHttpScraper):
    source_id = "foster_and_partners"
    source_name = "Foster + Partners"
    base_url = "https://www.fosterandpartners.com"
    news_url = "https://www.fosterandpartners.com/news"

    # Umbraco CMS API endpoint
    API_URL = "https://content.fosterandpartners.com/api/articles"
    IMAGE_BASE = "https://content.fosterandpartners.com"

    MAX_NEW_ARTICLES = 10

    # Not used (we override fetch_articles), but needed by base class
    card_selector = "article"
    title_selector = "h2"
    link_selector = "a"
    date_format = "%Y-%m-%dT%H:%M:%SZ"

    excluded_patterns = [
        "/news/$",
        "/news$",
        "/news/news-article-list/$",
        "/news/news-article-list$",
        "/news/type/",
    ]

    async def fetch_articles(self, hours: int = 24) -> list[dict]:
        """
        Fetch new articles via Umbraco CMS API.

        The standard StudioHttpScraper flow won't work because the news page
        is Angular SSR with no article data in raw HTML. Instead, we call the
        Umbraco API directly which returns structured JSON.
        """
        print(f"[{self.source_id}] Starting fetch via Umbraco CMS API...")
        await self._ensure_tracker()

        try:
            # Step 1: Fetch articles from API
            articles = await self._fetch_via_api()

            if not articles:
                print(f"[{self.source_id}] API returned no articles")
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

    async def _fetch_via_api(self) -> List[dict]:
        """
        Fetch articles from the Umbraco CMS API.

        Endpoint: https://content.fosterandpartners.com/api/articles
        Params: pageSize, pageIndex, orderBy, orderDirection
        Returns JSON object with:
            - count: number of articles on this page
            - totalCount: total articles available
            - data: array of article objects
        Each article object has:
            - title: article title
            - reference: slug for URL
            - date: ISO date string (e.g. "2026-02-10T00:00:00Z")
            - heroImage: path to hero image (e.g. "/media/bn4aswi1/image.jpg")
            - content: HTML snippet (first ~200 chars)
            - id: numeric ID
            - readMinutes: estimated read time
        """
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Referer": "https://www.fosterandpartners.com/",
            "Origin": "https://www.fosterandpartners.com",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                params = {
                    "pageSize": 15,
                    "pageIndex": 1,
                    "orderBy": "date",
                    "orderDirection": "descending",
                }

                # The API expects params as a JSON body in a query string format
                # Based on the SSR state, it uses a JSON-encoded params object
                api_url = f"{self.API_URL}"

                async with session.get(
                    api_url,
                    headers=headers,
                    params=params,
                    ssl=False
                ) as response:
                    if response.status != 200:
                        print(f"[{self.source_id}] API returned HTTP {response.status}")
                        # Try with JSON body format (as seen in SSR state)
                        return await self._fetch_via_api_json_body(session, headers)

                    data = await response.json()

            return self._parse_api_response(data)

        except Exception as e:
            print(f"[{self.source_id}] API error: {e}")
            return []

    async def _fetch_via_api_json_body(self, session, headers) -> List[dict]:
        """
        Fallback: The SSR state shows the API might expect a POST with JSON body.
        The URL pattern in the SSR state is:
        /api/articles{"pageSize":12,"pageIndex":1,"orderBy":"date","orderDirection":"descending"}
        This suggests the params might be passed as a JSON-encoded string in the URL or body.
        """
        try:
            # Try POST with JSON body
            body = {
                "pageSize": 15,
                "pageIndex": 1,
                "orderBy": "date",
                "orderDirection": "descending",
            }
            async with session.post(
                self.API_URL,
                headers={**headers, "Content-Type": "application/json"},
                json=body,
                ssl=False
            ) as response:
                if response.status != 200:
                    print(f"[{self.source_id}] POST API returned HTTP {response.status}")
                    # Try the quirky URL-encoded JSON format from SSR state
                    return await self._fetch_via_api_encoded(session, headers)

                data = await response.json()

            return self._parse_api_response(data)

        except Exception as e:
            print(f"[{self.source_id}] POST API error: {e}")
            return []

    async def _fetch_via_api_encoded(self, session, headers) -> List[dict]:
        """
        Last resort: The SSR state shows URLs like:
        /api/articles{"pageSize":12,"pageIndex":1,...}
        This is the Umbraco content delivery pattern where JSON params
        are appended directly to the URL path.
        """
        try:
            params_json = json.dumps({
                "pageSize": 15,
                "pageIndex": 1,
                "orderBy": "date",
                "orderDirection": "descending",
            }, separators=(',', ':'))

            url = f"{self.API_URL}{params_json}"
            print(f"[{self.source_id}] Trying encoded URL: {url[:100]}...")

            async with session.get(
                url,
                headers=headers,
                ssl=False
            ) as response:
                if response.status != 200:
                    print(f"[{self.source_id}] Encoded API returned HTTP {response.status}")
                    return []

                data = await response.json()

            return self._parse_api_response(data)

        except Exception as e:
            print(f"[{self.source_id}] Encoded API error: {e}")
            return []

    def _parse_api_response(self, data) -> List[dict]:
        """
        Parse the API response into a list of article dicts.
        The response format is:
        {
            "count": 12,
            "totalCount": 1059,
            "data": [
                {
                    "date": "2026-02-10T00:00:00Z",
                    "heroImage": "/media/bn4aswi1/image.jpg",
                    "title": "Article Title",
                    "reference": "article-slug",
                    ...
                }
            ]
        }
        """
        # Handle both direct array and wrapped object formats
        if isinstance(data, list):
            article_list = data
        elif isinstance(data, dict):
            article_list = data.get("data", [])
            total = data.get("totalCount", "?")
            print(f"[{self.source_id}] API reports {total} total articles")
        else:
            print(f"[{self.source_id}] Unexpected response format: {type(data)}")
            return []

        articles = []
        for item in article_list:
            try:
                title = item.get("title", "")
                reference = item.get("reference", "")
                date_str = item.get("date", "")
                hero_image = item.get("heroImage", "")

                if not title or not reference:
                    continue

                # Build full article URL
                url = f"{self.base_url}/news/news-article-list/{reference}/"

                # Parse date (ISO format: "2026-02-10T00:00:00Z")
                date_iso = None
                if date_str:
                    try:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        date_iso = dt.isoformat()
                    except ValueError:
                        pass

                # Build full image URL
                image_url = None
                if hero_image:
                    image_url = f"{self.IMAGE_BASE}{hero_image}"

                articles.append({
                    "url": url,
                    "title": title,
                    "date": date_iso,
                    "image_url": image_url,
                })

            except Exception as e:
                print(f"[{self.source_id}] Error parsing article: {e}")
                continue

        print(f"[{self.source_id}] API returned {len(articles)} articles")
        return articles

    def _is_valid_article_url(self, url: str) -> bool:
        if not super()._is_valid_article_url(url):
            return False
        if "fosterandpartners.com" not in url:
            return False
        path = url.split("fosterandpartners.com")[-1] if "fosterandpartners.com" in url else url
        clean_path = path.rstrip("/")
        skip_paths = [
            "/news", "/news/news-article-list",
            "/projects", "/studio", "/people",
            "/expertise", "/insights", "/careers", "/contact",
        ]
        return clean_path not in skip_paths


custom_scraper_registry.register(FosterAndPartnersScraper)
