import gzip
import re
import requests
from defusedxml import ElementTree as ET
from urllib.parse import urlsplit
from core.url_normalizer import normalize_many, normalize_url
from utils.exceptions import NetworkError

HEADERS = {"User-Agent": "SearchConsoleDiagnosticTool/2.0 (sitemap reader)"}
MATNAM_HOST = "matnam12.blogspot.com"


def _fetch(url, timeout=15):
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        body = response.content
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return response.url, body
    except requests.RequestException as exc:
        raise NetworkError(f"URL 가져오기 실패: {exc}") from exc


def _locs(body):
    try:
        root = ET.fromstring(body)
    except Exception as exc:
        raise NetworkError(f"사이트맵/RSS XML을 읽을 수 없습니다: {exc}") from exc
    return [(node.text or "").strip() for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() == "loc" and node.text]


def _site_url(raw, host, allowed_host=None):
    try:
        url = normalize_url(raw)
    except Exception:
        return None
    parsed = urlsplit(url)
    if parsed.hostname != host or (allowed_host and parsed.hostname != allowed_host):
        return None
    path = parsed.path.lower()
    if host.lower() in path or re.search(r"https?[^/]*blogspot\.com", path):
        return None
    return url


def collect(source_lines, limit, stop_event=None, progress=None, allowed_host=None):
    def cancelled():
        return stop_event is not None and stop_event.is_set()

    def report(message, count=0):
        if progress is not None:
            progress(message, count)

    lines = [line.strip() for line in source_lines.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise ValueError("URL을 입력하세요.")
    if len(lines) > 1:
        urls = []
        for line in lines:
            normalized = normalize_url(line)
            url = _site_url(normalized, urlsplit(normalized).hostname, allowed_host)
            if url:
                urls.append(url)
        urls = list(dict.fromkeys(urls))[:limit]
        report("입력한 URL을 정리했습니다.", len(urls))
        return None, urls
    source = lines[0]
    if "://" not in source:
        source = "https://" + source
    source = normalize_url(source)
    source_host = urlsplit(source).hostname
    if allowed_host and source_host != allowed_host:
        raise ValueError(f"matnam 사이트만 지원합니다: https://{MATNAM_HOST}/")
    parsed_source = source.lower()
    if ".xml" in parsed_source or "sitemap" in parsed_source:
        found, visited = [], set()
        queue = [source]
        while queue and len(found) < limit and len(visited) < 20:
            if cancelled():
                return None, []
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            report(f"사이트맵을 읽는 중: {current}", len(found))
            _, body = _fetch(current)
            for loc in _locs(body):
                if ".xml" in loc.lower() and len(found) < limit:
                    queue.append(loc)
                elif loc.startswith(("http://", "https://")):
                    url = _site_url(loc, source_host, allowed_host)
                    if url:
                        found.append(url)
        if found:
            urls = list(dict.fromkeys(found))[:limit]
            report("사이트맵에서 URL을 찾았습니다.", len(urls))
            return source, urls
        raise ValueError("사이트맵에서 글 URL을 찾지 못했습니다.")

    path = urlsplit(source).path
    if path not in ("", "/"):
        report("개별 URL을 준비했습니다.", 1)
        return source, [source]
    base = source.rstrip("/")
    if "blogspot." in base:
        if cancelled():
            return None, []
        feed = base + "/feeds/posts/default?alt=rss&max-results=" + str(limit)
        report("블로그 글 목록을 가져오는 중입니다.")
        try:
            _, body = _fetch(feed)
            root = ET.fromstring(body)
            links = []
            for node in root.iter():
                if node.tag.rsplit("}", 1)[-1].lower() == "link":
                    href = node.attrib.get("href") or (node.text or "").strip()
                    rel = node.attrib.get("rel", "alternate").lower()
                    if href.startswith(("https://", "http://")) and rel == "alternate" and "/feeds/" not in href:
                        url = _site_url(href, source_host, allowed_host)
                        if url:
                            links.append(url)
            if links:
                urls = list(dict.fromkeys(links))[:limit]
                report("블로그 글 URL을 찾았습니다.", len(urls))
                return base, urls
        except (NetworkError, ET.ParseError):
            report("글 목록을 읽지 못해 사이트맵을 확인합니다.")
    sitemap_candidates = [base + "/sitemap.xml", base + "/sitemap_index.xml"]
    for candidate in sitemap_candidates:
        if cancelled():
            return None, []
        report(f"사이트맵을 확인하는 중: {candidate}")
        try:
            _, body = _fetch(candidate)
            urls = [url for x in _locs(body)
                    if x.startswith(("http://", "https://")) and ".xml" not in x.lower()
                    if (url := _site_url(x, source_host, allowed_host))]
            if urls:
                report("사이트맵에서 URL을 찾았습니다.", len(urls[:limit]))
                return base, urls[:limit]
        except NetworkError:
            continue
    raise ValueError("사이트 URL에서 RSS 또는 사이트맵을 찾지 못했습니다. sitemap.xml 또는 개별 URL을 입력하세요.")

