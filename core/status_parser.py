import re
from core.models import Status

RULES = [
    (Status.NOINDEX, [r"noindex", r"색인 생성이 허용되지 않음"]),
    (Status.ROBOTS_BLOCKED, [r"blocked by robots", r"robots\.txt.*차단"]),
    (Status.NOT_FOUND, [r"not found\s*\(404\)", r"찾을 수 없음.*404", r"soft 404", r"소프트 404"]),
    (Status.SERVER_ERROR, [r"server error\s*\(5\d\d\)", r"서버 오류.*5\d\d"]),
    (Status.REDIRECT, [r"page with redirect", r"리디렉션이 포함된 페이지", r"리디렉션 오류"]),
    (Status.ALTERNATE_CANONICAL, [r"alternate page with proper canonical", r"duplicate, google chose",
        r"적절한 표준 태그가 포함된 대체 페이지", r"중복 페이지"]),
    (Status.CRAWLED_NOT_INDEXED, [r"crawled\s*[-–—]\s*currently not indexed", r"크롤링됨.*현재 색인이 생성되지"]),
    (Status.DISCOVERED_NOT_INDEXED, [r"discovered\s*[-–—]\s*currently not indexed", r"발견됨.*현재 색인이 생성되지"]),
    (Status.DISCOVERED_NOT_INDEXED, [r"url을 google에 등록할 수 있음", r"url can be indexed"]),
    (Status.TEMP_ERROR, [r"temporarily unavailable", r"일시적으로 사용할 수 없", r"quota.*exceeded", r"할당량.*초과"]),
]


def parse_status(text):
    value = re.sub(r"\s+", " ", text.lower())
    # The live test result can appear over the old inspection card, so give
    # its explicit positive result priority over stale redirect text.
    if re.search(r"url을 google에 등록할 수 있음|url can be indexed", value, re.I):
        return Status.DISCOVERED_NOT_INDEXED
    matches = [status for status, patterns in RULES if any(re.search(p, value, re.I) for p in patterns)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return Status.UNKNOWN
    if any(x in value for x in ("url is not on google", "url이 google에 등록되어 있지", "page is not indexed")):
        return Status.UNKNOWN
    if any(x in value for x in ("url is on google", "url이 google에 등록되어 있습니다", "페이지 색인이 생성됨")):
        return Status.INDEXED
    return Status.UNKNOWN

