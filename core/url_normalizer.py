import re
from urllib.parse import urlsplit, urlunsplit
from utils.exceptions import InvalidUrlError


def normalize_url(raw):
    value = raw.strip()
    try:
        p = urlsplit(value)
        if p.scheme.lower() not in ("http", "https") or not p.hostname or p.username or p.password:
            raise ValueError("http 또는 https URL이 필요합니다.")
        if re.search(r"[\s\\\x00-\x1f]", value):
            raise ValueError("URL 안에 공백 또는 제어 문자가 있습니다.")
        host = p.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = "[" + host + "]"
        if p.port and (p.scheme.lower(), p.port) not in (("http", 80), ("https", 443)):
            host += ":" + str(p.port)
        query = []
        for part in p.query.split("&"):
            key = part.partition("=")[0].lower()
            if key.startswith("utm_") or key in {"gclid", "fbclid"}:
                continue
            if p.hostname.lower().endswith(".blogspot.com") and key == "m":
                continue
            if part:
                query.append(part)
        return urlunsplit((p.scheme.lower(), host, p.path or "/", "&".join(query), ""))
    except (ValueError, UnicodeError) as exc:
        raise InvalidUrlError(f"유효하지 않은 URL: {value} ({exc})") from exc


def normalize_many(lines):
    return list(dict.fromkeys(normalize_url(value) for value in lines if value.strip()))


def is_in_property(url, property_url):
    if property_url.startswith("sc-domain:"):
        host = urlsplit(url).hostname or ""
        domain = property_url[10:].strip().lower()
        return bool(domain) and (host == domain or host.endswith("." + domain))
    prop = urlsplit(normalize_url(property_url))
    target = urlsplit(url)
    prefix = prop.path.rstrip("/")
    return target.scheme == prop.scheme and target.netloc == prop.netloc and (
        not prefix or target.path == prefix or target.path.startswith(prefix + "/"))
