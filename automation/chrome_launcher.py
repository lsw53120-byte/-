"""Launch an isolated Chrome profile with loopback-only DevTools for Selenium attach."""
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from utils.exceptions import BrowserConnectionError

DEBUG_ADDRESS = "127.0.0.1:9222"
VERSION_URL = "http://127.0.0.1:9222/json/version"
SEARCH_CONSOLE_URL = "https://search.google.com/search-console"


def is_debug_chrome_available():
    try:
        with urllib.request.urlopen(VERSION_URL, timeout=0.75) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _chrome_executable():
    candidates = []
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidates.append(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BrowserConnectionError("Chrome 실행 파일을 찾지 못했습니다. Google Chrome을 설치한 뒤 다시 시도하세요.")


def _reject_default_profile(profile: Path):
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return
    standard_root = (Path(local_app_data) / "Google" / "Chrome" / "User Data").resolve()
    candidate = profile.resolve()
    if candidate == standard_root or standard_root in candidate.parents:
        raise BrowserConnectionError(
            "Chrome 기본 사용자 프로필은 원격 디버깅에 사용할 수 없습니다. "
            "이전 자동화 도구의 별도 chrome_profile 폴더를 선택하거나 연결용 프로필을 사용하세요."
        )


def open_connected_chrome(profile: Path):
    """Reuse an already-debuggable Chrome; otherwise start the persistent app profile."""
    if is_debug_chrome_available():
        return "기존 원격 디버깅 Chrome에 연결할 수 있습니다."
    _reject_default_profile(profile)
    profile.mkdir(parents=True, exist_ok=True)
    command = [
        str(_chrome_executable()),
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=9222",
        f"--user-data-dir={profile.resolve()}",
        "--no-first-run",
        "--new-window",
        SEARCH_CONSOLE_URL,
    ]
    try:
        subprocess.Popen(command, close_fds=True)
    except OSError as exc:
        raise BrowserConnectionError(f"연결용 Chrome을 열 수 없습니다: {exc}") from exc
    for _ in range(40):
        if is_debug_chrome_available():
            return "연결용 Chrome을 열었습니다. 로그인 후 이 창을 그대로 두세요."
        time.sleep(0.25)
    raise BrowserConnectionError(
        "Chrome이 원격 디버깅 포트 9222를 열지 못했습니다. 선택한 프로필을 사용하는 Chrome 창을 직접 닫은 뒤 다시 시도하거나 포트 사용 여부를 확인하세요."
    )
