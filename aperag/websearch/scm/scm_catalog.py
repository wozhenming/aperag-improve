# Copyright 2025 ApeCloud, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""scm.com.cn (广东省计量科学研究院) catalog browsing.

Loads the site map (scm_site.yaml) and parses article list pages:
each list page is statically rendered with 10 items shaped as
`<a href="/news/detail-NNN.html"><h2>标题</h2><i>日期</i></a>`,
with pagination at `{url}/{page}.html`.
"""

import logging
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_SITE_MAP_PATH = Path(__file__).parent / "scm_site.yaml"

# Article item: <a href="/news/detail-NNN.html" ...><h2>title</h2><i>date</i></a>
_ARTICLE_RE = re.compile(
    r'<a href="(/news/detail-\d+\.html)"[^>]*>\s*<h2>(.*?)</h2>\s*<i>(.*?)</i>',
    re.S,
)

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ApeRAG/1.0; +https://aperag.ai)",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
}


class ScmCatalog:
    """Site map + list page parser for www.scm.com.cn."""

    def __init__(self, site_map_path: Path = _SITE_MAP_PATH):
        import yaml

        with open(site_map_path, "r", encoding="utf-8") as f:
            self.site_map = yaml.safe_load(f) or {}
        self.base_url = str(self.site_map.get("base_url", "https://www.scm.com.cn")).rstrip("/")
        self.categories = self.site_map.get("categories", [])

    def list_categories(self) -> list[dict]:
        """All categories (name, type, url) for tool descriptions / validation."""
        return [{"name": c.get("name"), "type": c.get("type"), "url": c.get("url")} for c in self.categories]

    def find_category(self, name: str) -> dict | None:
        """Find a category by exact or partial name match."""
        name = (name or "").strip()
        if not name:
            return None
        for c in self.categories:
            if c.get("name") == name:
                return c
        # partial / contains match
        for c in self.categories:
            if name in c.get("name", ""):
                return c
        return None

    async def fetch_list_page(self, category: dict, page: int = 1) -> str:
        """GET a list page (page 1 = base URL, page N = {url-without-.html}/{N}.html)."""
        url_path = category.get("url", "").strip()
        if page > 1:
            base = url_path[:-5] if url_path.endswith(".html") else url_path.rstrip("/")
            url_path = f"{base}/{page}.html"
        url = f"{self.base_url}{url_path}"
        async with httpx.AsyncClient(timeout=30.0, headers=_DEFAULT_HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

    def parse_articles(self, html: str) -> list[dict]:
        """Extract (title, date, url) items from a list page."""
        results = []
        for url, title, date in _ARTICLE_RE.findall(html):
            results.append(
                {
                    "title": re.sub(r"\s+", " ", title).strip(),
                    "date": date.strip(),
                    "url": f"{self.base_url}{url.strip()}",
                }
            )
        return results

    async def list_articles(self, category_name: str, page: int = 1, keyword: str = "") -> dict:
        """Browse a list-type category; returns parsed articles (optionally filtered)."""
        category = self.find_category(category_name)
        if not category:
            return {"error": f"未知栏目「{category_name}」。可用栏目请用 list_categories() 查看。"}
        if category.get("type") != "list":
            return {
                "error": (
                    f"「{category_name}」是静态信息页（非文章列表），无需 scm_list。"
                    f"请直接用 web_read 读取 {self.base_url}{category.get('url')}"
                ),
                "url": f"{self.base_url}{category.get('url')}",
            }
        try:
            html = await self.fetch_list_page(category, page=max(1, page))
        except Exception as e:
            logger.warning(f"scm list fetch failed for {category_name}: {e}")
            return {"error": f"抓取栏目「{category_name}」失败: {str(e)}"}

        articles = self.parse_articles(html)
        kw = (keyword or "").strip()
        if kw:
            articles = [a for a in articles if kw.lower() in a["title"].lower()]

        return {
            "category": category.get("name"),
            "page": page,
            "found": len(articles),
            "articles": articles[:10],
            "hint": "用 web_read 读取 article 的 url 获取正文。",
        }


scm_catalog = ScmCatalog()
