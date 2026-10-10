from datetime import datetime, timedelta, timezone
from core.models import Settings, Status

# The user explicitly opted into automatic requests.  REDIRECT is included so
# Search Console can receive the request when its result card exposes the
# request link; Google still decides whether the URL can be accepted.
REQUESTABLE = {Status.DISCOVERED_NOT_INDEXED, Status.CRAWLED_NOT_INDEXED, Status.REDIRECT}
ADVICE = {
    Status.INDEXED: "정상 색인입니다. 추가 요청이 필요하지 않습니다.",
    Status.DISCOVERED_NOT_INDEXED: "사이트맵과 내부 링크, 서버 접근성을 확인하세요.",
    Status.CRAWLED_NOT_INDEXED: "콘텐츠 독창성·품질, 중복 여부와 내부 링크를 확인하세요.",
    Status.REQUESTED_RECENTLY: "최근 요청의 처리 결과를 기다린 뒤 재검사하세요.",
    Status.ALTERNATE_CANONICAL: "Google 선택 canonical과 원본 URL을 확인하세요.",
    Status.REDIRECT: "리디렉션 최종 목적지 URL을 검사하세요.",
    Status.NOINDEX: "페이지의 noindex 설정을 검토하세요.",
    Status.ROBOTS_BLOCKED: "robots.txt의 해당 경로 차단을 확인하세요.",
    Status.NOT_FOUND: "404 응답 또는 삭제된 URL인지 확인하세요.",
    Status.SERVER_ERROR: "호스팅 서버의 오류 응답을 확인하세요.",
    Status.TEMP_ERROR: "일시 오류입니다. 다음 실행에서 재검사하세요.",
    Status.LOGIN_REQUIRED: "Google 계정에 로그인하고 속성 접근 권한을 확인하세요.",
    Status.TIMEOUT: "연결 상태를 확인한 뒤 재검사하세요.",
    Status.UNKNOWN: "상태를 확실히 판독하지 못했습니다. 직접 확인하세요.",
}


def _date(value):
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def request_decision(status, settings, latest_attempt, daily_count, service_blocked=False):
    if status not in REQUESTABLE:
        return False, ADVICE[status]
    if not settings.auto_request:
        return False, "검사 전용 설정입니다. 자동 색인 요청이 꺼져 있습니다."
    if service_blocked:
        return False, "Search Console에서 한도 또는 확인 화면을 표시했습니다."
    # Redirect results are explicitly included in the user's matnam workflow:
    # the inspected URL is not the final page, so a fresh run must be allowed
    # to submit the request for the current result instead of being hidden by
    # a stale prior attempt record. The daily limit still prevents runaway
    # submissions.
    if status != Status.REDIRECT and latest_attempt and datetime.now(timezone.utc) < _date(latest_attempt) + timedelta(days=settings.request_cooldown_days):
        return False, "최근 요청 시도 이후 대기 기간입니다."
    if daily_count >= settings.daily_request_limit:
        return False, "설정된 일일 요청 한도에 도달했습니다."
    return True, "요청 가능한 상태이며 대기 기간과 일일 한도를 충족했습니다."

