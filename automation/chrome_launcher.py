"""Launch an isolated Chrome profile with loopback-only DevTools for Selenium attach."""
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from utils.exceptions import BrowserConnectionError

SEARCH_CONSOLE_URL = "https://search.google.com/search-console"
PORT_FILE = ".searchconsole_debug_port"


def _version_url(port):
    return f"http://127.0.0.1:{port}/json/version"


def is_debug_chrome_available(port):
    try:
        with urllib.request.urlopen(_version_url(port), timeout=0.75) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _remembered_port(profile: Path):
    try:
        value = int((profile / PORT_FILE).read_text(encoding="ascii").strip())
        return value if 1024 <= value <= 65535 else None
    except (OSError, ValueError):
        return None


def _free_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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
    _reject_default_profile(profile)
    profile.mkdir(parents=True, exist_ok=True)
    remembered = _remembered_port(profile)
    if remembered and is_debug_chrome_available(remembered):
        return remembered, "기존 연결용 Chrome에 연결할 수 있습니다."
    port = _free_loopback_port()
    command = [
        str(_chrome_executable()),
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile.resolve()}",
        "--no-first-run",
        "--new-window",
        SEARCH_CONSOLE_URL,
    ]
    try:
        subprocess.Popen(command, close_fds=True)
    except OSError as exc:
        raise BrowserConnectionError(f"연결용 Chrome을 열 수 없습니다: {exc}") from exc
    for _ in range(60):
        if is_debug_chrome_available(port):
            try:
                (profile / PORT_FILE).write_text(str(port), encoding="ascii")
            except OSError:
                pass
            return port, "연결용 Chrome을 열었습니다. 로그인 후 이 창을 그대로 두세요."
        time.sleep(0.25)
    raise BrowserConnectionError(
        "Chrome 연결 포트를 열지 못했습니다. 선택한 연결용 프로필의 Chrome 창을 닫은 뒤 다시 시도하세요."
    )
