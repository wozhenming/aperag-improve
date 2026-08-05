"""
Trafilatura Reader Provider

Lightweight web content reading implementation using Trafilatura.
No browser dependencies - perfect for lightweight deployments.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import List

import aiohttp

try:
    import markdownify
    import trafilatura

    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

from aperag.schema.view_models import WebReadResultItem
from aperag.websearch.reader.base_reader import BaseReaderProvider
from aperag.websearch.utils.content_processor import ContentProcessor
from aperag.websearch.utils.url_validator import URLValidator

logger = logging.getLogger(__name__)


class ReaderProviderError(Exception):
    """Exception raised by reader providers."""

    pass


class TrafilaturaProvider(BaseReaderProvider):
    """
    Trafilatura reader provider implementation.

    Uses Trafilatura for content extraction - no browser required.
    Lightweight, fast, but limited to static content.
    """

    def __init__(self, config: dict = None):
        """
        Initialize Trafilatura provider.

        Args:
            config: Provider configuration
        """
        super().__init__(config)

        if not HAS_TRAFILATURA:
            raise ReaderProviderError("Trafilatura is not installed. Run: uv add trafilatura markdownify")

    async def read(
        self,
        url: str,
        timeout: int = 30,
        locale: str = "zh-CN",
        method: str = "GET",
        body: dict = None,
        body_type: str = "form",
        extra_headers: dict = None,
    ) -> WebReadResultItem:
        """
        Read content from a single URL using Trafilatura.

        Args:
            url: URL to read content from
            timeout: Request timeout in seconds
            locale: Browser locale (used for User-Agent)
            method: HTTP method (GET/POST/PUT/PATCH/DELETE) — POST is useful for
                AJAX search/query endpoints that render results via JS
            body: Request body (JSON object) for POST/PUT/PATCH
            body_type: "form" (x-www-form-urlencoded) or "json"
            extra_headers: Additional HTTP headers merged over defaults

        Returns:
            Web read result item

        Raises:
            ReaderProviderError: If reading fails
        """
        if not url or not url.strip():
            raise ReaderProviderError("URL cannot be empty")

        # Normalize and validate URL. NOTE: only normalize for GET — normalize_url
        # strips the trailing slash, which breaks AJAX endpoints where the slash is
        # part of the route (e.g. POST /search/news/ vs /search/news → 404/homepage).
        url = url.strip()
        if (method or "GET").upper() == "GET":
            url = URLValidator.normalize_url(url)
        if not URLValidator.is_valid_url(url):
            return WebReadResultItem(
                url=url,
                status="error",
                error="Invalid URL format",
                error_code="INVALID_URL",
            )

        try:
            # Fetch HTML content
            html_content = await self._fetch_html(
                url, timeout, locale, method=method, body=body, body_type=body_type, extra_headers=extra_headers
            )
            if not html_content:
                return WebReadResultItem(
                    url=url,
                    status="error",
                    error="Failed to fetch HTML content",
                    error_code="FETCH_ERROR",
                )

            # Extract main content using Trafilatura
            extracted_text = trafilatura.extract(
                html_content,
                output_format="xml",  # Get structured output
                include_comments=False,
                include_tables=True,
                include_links=True,
                deduplicate=True,
                favor_precision=True,  # Prefer quality over quantity
                no_fallback=False,  # Use fallback extraction if needed
            )

            if not extracted_text:
                # Fallback to simple text extraction
                extracted_text = trafilatura.extract(
                    html_content,
                    output_format="txt",
                    no_fallback=True,
                    favor_recall=True,
                )

            # Container fallback: the page body often lives in unsemantic
            # containers (div.Work_Text / div.Trends_Ct on scm.com.cn) that
            # Trafilatura's precision mode discards or only partially extracts
            # (e.g. stops mid-page on Word-exported content). If the known
            # content containers hold substantially more text than the
            # Trafilatura result, the extraction was incomplete — use the
            # containers instead.
            container_text = self._extract_content_containers(html_content)
            if container_text and (not extracted_text or len(container_text) > len(extracted_text.strip()) * 1.3):
                extracted_text = container_text

            if not extracted_text:
                # Final fallback for AJAX endpoints: they often return HTML
                # fragments or JSON without a full page structure that
                # Trafilatura can extract — return the raw payload instead.
                stripped_content = html_content.strip()
                if not stripped_content:
                    return WebReadResultItem(
                        url=url,
                        status="error",
                        error="Failed to extract content",
                        error_code="EXTRACTION_ERROR",
                    )
                if stripped_content.startswith(("{", "[")):
                    import json as _json

                    try:
                        data = _json.loads(stripped_content)
                        extracted_text = _json.dumps(data, ensure_ascii=False, indent=2)
                    except Exception:
                        extracted_text = stripped_content
                else:
                    extracted_text = stripped_content

            # Convert to Markdown
            content = self._to_markdown(extracted_text)

            # Process content
            content = ContentProcessor.sanitize_markdown(content)

            # Append the page's internal links so multi-hop retrieval works:
            # the model can see which sub-pages exist (e.g. the 国家中心 sidebar
            # entry on the org intro page) and follow them with another web_read.
            page_links = self._extract_page_links(html_content, url)
            if page_links:
                content = f"{content}\n\n## 页面内链接\n{page_links}"

            title = ContentProcessor.extract_title_from_content(content)

            # Try to get title from metadata if not found in content
            if not title:
                metadata = trafilatura.extract_metadata(html_content)
                if metadata and metadata.title:
                    title = metadata.title
                else:
                    title = "Untitled"

            return WebReadResultItem(
                url=url,
                status="success",
                title=title,
                content=content,
                extracted_at=datetime.now(),
                word_count=ContentProcessor.count_words(content),
                token_count=ContentProcessor.estimate_tokens(content),
            )

        except Exception as e:
            logger.error(f"Trafilatura read failed for {url}: {e}")
            return WebReadResultItem(
                url=url,
                status="error",
                error=f"Read failed: {str(e)}",
                error_code="READ_ERROR",
            )

    async def _fetch_html(
        self,
        url: str,
        timeout: int,
        locale: str,
        method: str = "GET",
        body: dict = None,
        body_type: str = "form",
        extra_headers: dict = None,
    ) -> str:
        """
        Fetch HTML content from URL, optionally with a POST/PUT/PATCH body.

        Args:
            url: URL to fetch
            timeout: Request timeout
            locale: Locale for User-Agent
            method: HTTP method (GET/POST/PUT/PATCH/DELETE)
            body: Request body (JSON object) for POST/PUT/PATCH
            body_type: "form" (x-www-form-urlencoded) or "json"
            extra_headers: Additional HTTP headers merged over defaults

        Returns:
            HTML content string
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ApeRAG/1.0; +https://aperag.ai)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": f"{locale.replace('-', '_')},en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        if extra_headers:
            headers.update({str(k): str(v) for k, v in extra_headers.items()})

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), headers=headers) as session:
                method = (method or "GET").upper()
                if method in ("POST", "PUT", "PATCH"):
                    if body_type == "json":
                        req_kwargs = {"json": body or {}}
                    else:
                        req_kwargs = {"data": body or {}}
                    async with session.request(method, url, **req_kwargs) as response:
                        return await self._read_response(response, url)
                else:
                    async with session.get(url) as response:
                        return await self._read_response(response, url)
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return ""

    @staticmethod
    async def _read_response(response, url: str) -> str:
        """Read a successful response body, or log and return empty on failure."""
        if response.status == 200:
            return await response.text()
        logger.warning(f"HTTP {response.status} for {url}")
        return ""

    # Content containers whose text is page body on legacy/simple sites
    # (scm.com.cn info pages put body text in div.Work_Text / div.Trends_Ct
    # without <p> structure, which Trafilatura's precision mode discards).
    _CONTENT_CONTAINER_CLASSES = [
        "Work_Text",
        "Trends_Ct",
        "Dynamics_Ct",
        "News_Ct",
        "Base_Ct",
        "Article",
        "Content",
        "article-content",
        "news-content",
    ]

    # Ancestor classes that mark chrome (header/footer/nav) — their links are noise
    _CHROME_ANCESTORS = [
        "HeaderFlix",
        "b_head",
        "Mb_head",
        "menu-li",
        "Footer",
        "am_subfooterdiv",
        "am_bootom",
        "subnav_ul",
        "Navdown",
        "Search_Popup",
        "MaskShow",
        "go_top",
    ]

    def _extract_page_links(self, html: str, page_url: str) -> str:
        """List meaningful in-page links (anchor text → absolute URL) for multi-hop reads.

        Excludes chrome links (header/footer/nav menus) and duplicate/noise anchors.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return ""
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            return ""

        from urllib.parse import urljoin

        base_url = urljoin(page_url, "/")
        entries: list[tuple[str, str]] = []
        seen_urls: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
                continue
            # skip chrome (header/footer/nav) links
            chrome = any(a.find_parent(class_=cls) is not None for cls in self._CHROME_ANCESTORS)
            if chrome:
                continue
            text = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
            if not text or len(text) > 40:
                continue
            url = urljoin(base_url, href)
            # dedup by URL + anchor text
            key = (url, text)
            if key in seen_urls:
                continue
            seen_urls.add(key)
            entries.append((text, url))

        # keep most relevant: sidebar/nav links usually come first in DOM order;
        # cap at 30 to avoid noise
        lines = []
        for text, url in entries[:30]:
            lines.append(f"- {text}: {url}")
        return "\n".join(lines)

    def _extract_content_containers(self, html: str) -> str:
        """Merge known content containers, preserving paragraph structure.

        Containers are converted to Markdown (so <p> paragraphs, <h2> titles
        and <li> items survive) and deduped by containment — an outer container
        (e.g. .Trends_Ct) includes every inner block (e.g. .Work_Text).
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return ""
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            return ""

        selector = ", ".join(f".{cls}" for cls in self._CONTENT_CONTAINER_CLASSES)
        parts: list[str] = []
        try:
            nodes = soup.select(selector)
        except Exception:
            return ""
        for node in nodes:
            text = self._container_to_markdown(node)
            if len(text) < 20:
                continue
            # Dedup by containment: an outer container's text includes its
            # children (e.g. .Trends_Ct includes every .Work_Text block).
            if any(text in p for p in parts):
                continue
            parts = [p for p in parts if p not in text]
            parts.append(text)
        parts.sort(key=len, reverse=True)
        # The largest containers are the page body; tiny ones are nav/footer fragments
        return "\n\n".join(parts[:3])

    @staticmethod
    def _container_to_markdown(node) -> str:
        """Convert a container element to Markdown, preserving paragraphs/lists.

        Falls back to newline-separated text if markdownify is unavailable.
        """
        try:
            import markdownify

            md = markdownify.markdownify(
                str(node),
                heading_style="ATX",
                bullets="-",
                escape_asterisks=False,
                escape_underscores=False,
            )
            md = re.sub(r"\n{3,}", "\n\n", md)
            md = re.sub(r"[ \t]+", " ", md)
            return md.strip()
        except Exception:
            text = node.get_text("\n", strip=True)
            return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _to_markdown(self, extracted_content: str) -> str:
        """
        Convert extracted content to Markdown.

        Args:
            extracted_content: Content from Trafilatura

        Returns:
            Markdown content
        """
        try:
            # If content is XML format, convert to HTML first then to Markdown
            if extracted_content.strip().startswith("<"):
                # Convert XML/HTML to Markdown
                markdown_content = markdownify.markdownify(
                    extracted_content,
                    heading_style="ATX",  # Use # for headings
                    bullets="-",  # Use - for lists
                    escape_asterisks=False,
                    escape_underscores=False,
                )
                return markdown_content
            else:
                # Already plain text, just return
                return extracted_content
        except Exception as e:
            logger.warning(f"Markdown conversion failed: {e}")
            return extracted_content

    async def read_batch(
        self,
        urls: List[str],
        timeout: int = 30,
        locale: str = "zh-CN",
        max_concurrent: int = 3,
        method: str = "GET",
        body: dict = None,
        body_type: str = "form",
        extra_headers: dict = None,
    ) -> List[WebReadResultItem]:
        """
        Read content from multiple URLs concurrently.

        Args:
            urls: List of URLs to read content from
            timeout: Request timeout in seconds
            locale: Browser locale
            max_concurrent: Maximum concurrent requests
            method: HTTP method (GET/POST/PUT/PATCH/DELETE)
            body: Request body (JSON object) for POST/PUT/PATCH
            body_type: "form" (x-www-form-urlencoded) or "json"
            extra_headers: Additional HTTP headers merged over defaults

        Returns:
            List of web read result items
        """
        if not urls:
            return []

        # Normalize URLs
        normalized_urls = [URLValidator.normalize_url(url.strip()) for url in urls]

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def read_single(url: str) -> WebReadResultItem:
            async with semaphore:
                return await self.read(
                    url=url,
                    timeout=timeout,
                    locale=locale,
                    method=method,
                    body=body,
                    body_type=body_type,
                    extra_headers=extra_headers,
                )

        # Execute all reads concurrently
        try:
            results = await asyncio.gather(*[read_single(url) for url in normalized_urls], return_exceptions=True)

            # Handle exceptions in results
            final_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Batch read failed for {normalized_urls[i]}: {result}")
                    final_results.append(
                        WebReadResultItem(
                            url=normalized_urls[i],
                            status="error",
                            error=f"Batch read failed: {str(result)}",
                            error_code="BATCH_ERROR",
                        )
                    )
                else:
                    final_results.append(result)

            return final_results

        except Exception as e:
            logger.error(f"Batch read failed: {e}")
            raise ReaderProviderError(f"Batch read failed: {str(e)}")

    async def close(self):
        """Close and cleanup resources."""
        # No resources to close
        pass

    def get_provider_info(self) -> dict:
        """
        Get provider information.

        Returns:
            Provider information dictionary
        """
        return {
            "name": "Trafilatura",
            "description": "Lightweight content extraction without browser dependencies",
            "supports_javascript": False,
            "supports_spa": False,
            "output_format": "markdown",
            "free": True,
            "requires_api_key": False,
            "lightweight": True,
        }
