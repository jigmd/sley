import ipaddress
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

MAX_PAGES = 25
MAX_PAGE_CHARACTERS = 1_000_000


def normalize_public_url(url: str) -> str:
    normalized, _fragment = urldefrag(url.strip())
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https and include a host")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not supported")

    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("local hosts are not crawl targets")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("private and non-routable addresses are not crawl targets")

    # Accessing port also validates malformed values such as :99999.
    _validated_port = parsed.port
    return normalized


def url_origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    default_port = 443 if parsed.scheme == "https" else 80
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port or default_port


class WebCrawler:
    """Crawl a small set of pages from one trusted public origin."""

    def __init__(self, base_url: str, max_pages: int = 10):
        if not isinstance(max_pages, int) or not 1 <= max_pages <= MAX_PAGES:
            raise ValueError(f"max_pages must be between 1 and {MAX_PAGES}")
        self.base_url = normalize_public_url(base_url)
        self.origin = url_origin(self.base_url)
        self.max_pages = max_pages
        self.visited: set[str] = set()

    def is_valid_url(self, url: str) -> bool:
        try:
            normalized = normalize_public_url(url)
        except ValueError:
            return False
        return url_origin(normalized) == self.origin

    def extract_page_content(self, url: str) -> dict:
        response = requests.get(
            url,
            timeout=10,
            allow_redirects=False,
            headers={"User-Agent": "Sley cookbook crawler/1.0"},
        )
        if 300 <= response.status_code < 400:
            raise RuntimeError(
                "redirects are disabled so every fetched URL is validated"
            )
        response.raise_for_status()
        if len(response.text) > MAX_PAGE_CHARACTERS:
            raise ValueError("page is too large for this example")

        soup = BeautifulSoup(response.text, "html.parser")
        links = []
        for link in soup.find_all("a"):
            href = link.get("href")
            if not href:
                continue
            absolute_url = urldefrag(urljoin(url, href))[0]
            if self.is_valid_url(absolute_url):
                links.append(absolute_url)

        return {
            "url": url,
            "title": soup.title.get_text(strip=True) if soup.title else "",
            "text": soup.get_text(separator="\n", strip=True),
            "links": links,
        }

    def crawl(self) -> list[dict]:
        to_visit = deque([self.base_url])
        queued = {self.base_url}
        results = []

        while to_visit and len(self.visited) < self.max_pages:
            url = to_visit.popleft()
            queued.remove(url)
            if url in self.visited:
                continue

            print(f"Crawling: {url}")
            self.visited.add(url)
            content = self.extract_page_content(url)
            results.append(content)

            for discovered in content["links"]:
                if discovered not in self.visited and discovered not in queued:
                    to_visit.append(discovered)
                    queued.add(discovered)

        return results
