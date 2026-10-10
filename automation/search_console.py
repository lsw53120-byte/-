import logging
import re
from pathlib import Path
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from core.models import Inspection, Status
from core.status_parser import parse_status
from utils.exceptions import BrowserConnectionError, LoginRequiredError, SearchConsoleTimeout, IndexRequestError
from automation.chrome_launcher import is_debug_chrome_available

URL_INSPECTION = "https://search.google.com/search-console"
SEARCH_SELECTORS = [
    (By.CSS_SELECTOR, "input[aria-label*='URL']"),
    (By.CSS_SELECTOR, "input[placeholder*='URL']"),
    (By.CSS_SELECTOR, "input[aria-label*='URL 검사']"),
]


class SearchConsole:
    def __init__(self, artifact_root: Path, timeout=45, logger=None):
        self.artifact_root = artifact_root
        self.timeout = timeout
        self.log = logger or logging.getLogger("search_console")
        self.driver = None

    def start(self, debug_port):
        if not is_debug_chrome_available(debug_port):
            raise BrowserConnectionError(
                "연결 가능한 Chrome을 찾지 못했습니다. 앱에서 [로그인 브라우저 열기]를 누른 뒤 Chrome 창을 열어 두세요."
            )
        options = Options()
        options.debugger_address = f"127.0.0.1:{debug_port}"
        try:
            self.driver = webdriver.Chrome(options=options)
            if not self.driver.window_handles:
                raise BrowserConnectionError("연결된 Chrome 창이 없습니다.")
            if "search.google.com/search-console" not in self.driver.current_url:
                self.driver.execute_script("window.open(arguments[0], '_blank')", URL_INSPECTION)
                self.driver.switch_to.window(self.driver.window_handles[-1])
        except WebDriverException as exc:
            if self.driver:
                try:
                    self.driver.service.stop()
                except Exception:
                    self.log.exception("Could not stop ChromeDriver after failed attach")
            self.driver = None
            raise BrowserConnectionError(
                f"열려 있는 Chrome에 연결하지 못했습니다. Chrome과 Selenium 버전을 확인하세요: {exc}"
            ) from exc
        return self.driver

    def _search_box(self):
        deadline = self.timeout
        last = None
        for by, selector in SEARCH_SELECTORS:
            try:
                return WebDriverWait(self.driver, min(deadline, 8)).until(
                    EC.element_to_be_clickable((by, selector)))
            except TimeoutException as exc:
                last = exc
        body = self.driver.find_element(By.TAG_NAME, "body").text.lower()
        if "sign in" in body or "로그인" in body or "계정 선택" in body:
            raise LoginRequiredError("연결한 Chrome에서 Google 계정에 로그인한 뒤 이어서 실행하세요.")
        raise SearchConsoleTimeout(f"URL 검사 입력창을 찾지 못했습니다: {last}")

    def inspect(self, url):
        try:
            box = self._search_box()
            box.click()
            box.send_keys(Keys.CONTROL, "a")
            box.send_keys(url)
            box.send_keys(Keys.ENTER)
            WebDriverWait(self.driver, self.timeout).until(
                lambda d: self._result_ready(d))
            body = self.driver.find_element(By.TAG_NAME, "body").text
            status = parse_status(body)
            if status == Status.UNKNOWN and any(x in body.lower() for x in ("sign in", "로그인", "계정 선택")):
                raise LoginRequiredError("Google 로그인이 필요합니다.")
            canonical = self._canonical(body)
            return Inspection(status=status, raw=body[:4000], canonical_url=canonical)
        except LoginRequiredError:
            raise
        except TimeoutException as exc:
            self._capture(url)
            raise SearchConsoleTimeout(f"URL 검사 결과 대기 시간이 초과되었습니다: {url}") from exc
        except WebDriverException as exc:
            self._capture(url)
            raise SearchConsoleTimeout(f"브라우저 작업 실패: {exc}") from exc

    @staticmethod
    def _result_ready(driver):
        try:
            body = driver.find_element(By.TAG_NAME, "body").text.lower()
            return any(token in body for token in (
                "url is on google", "url is not on google", "url이 google에 등록",
                "discovered - currently", "crawled - currently", "발견됨", "크롤링됨",
                "현재 색인이 생성되지", "페이지 색인이 생성됨"))
        except WebDriverException:
            return False

    @staticmethod
    def _canonical(body):
        match = re.search(r"(?:user-declared canonical|사용자 선언 표준 URL)\s*[:：]?\s*(https?://\S+)", body, re.I)
        return match.group(1).rstrip(".,)") if match else None

    def request_indexing(self, url):
        """Click request only after an explicit app policy decision; confirm exact dialog action."""
        before = self.driver.find_element(By.TAG_NAME, "body").text.lower()
        if any(x in before for x in ("quota", "limit exceeded", "할당량", "요청 한도")):
            raise IndexRequestError("Google 요청 한도 안내가 표시되었습니다.")
        candidates = self.driver.find_elements(
            By.XPATH,
            "//*[self::button or @role='button']["
            "contains(@aria-label,'Request indexing') or contains(@aria-label,'색인 생성 요청') or "
            "contains(@aria-label,'색인 재요청') or contains(normalize-space(.),'Request indexing') or "
            "contains(normalize-space(.),'색인 생성 요청') or contains(normalize-space(.),'색인 재요청')]"
        )
        candidates = [button for button in candidates if button.is_displayed() and button.is_enabled()]
        if not candidates:
            raise IndexRequestError("화면에서 색인 생성 요청 버튼을 찾지 못했습니다.")
        self._click_visible(candidates[0])
        try:
            def accepted(driver):
                text = driver.find_element(By.TAG_NAME, "body").text.lower()
                return any(word in text for word in (
                    "indexing requested", "request accepted", "요청이 제출", "색인 생성 요청됨"))
            def confirm_button(driver):
                dialogs = driver.find_elements(By.CSS_SELECTOR, "[role='dialog']")
                scope = dialogs[-1] if dialogs else driver
                options = scope.find_elements(By.XPATH,
                    ".//*[self::button or @role='button'][normalize-space()='Request indexing' or normalize-space()='색인 생성 요청' or normalize-space()='요청 보내기']")
                visible = [button for button in options if button.is_displayed() and button.is_enabled()]
                return visible[-1] if visible else False
            try:
                WebDriverWait(self.driver, 25).until(lambda d: accepted(d) or confirm_button(d))
            except TimeoutException:
                raise IndexRequestError("요청 확인 또는 접수 상태를 확인하지 못했습니다.")
            if not accepted(self.driver):
                confirm = confirm_button(self.driver)
                if not confirm:
                    raise IndexRequestError("확인 버튼을 찾지 못했습니다.")
                self._click_visible(confirm)
            WebDriverWait(self.driver, 20).until(
                accepted)
            return "Google 화면에서 요청 접수 확인"
        except TimeoutException as exc:
            self._capture(url)
            raise IndexRequestError("요청 접수 확인 문구를 확인하지 못했습니다. 요청이 전송됐는지 Search Console에서 확인하세요.") from exc

    def _click_visible(self, element):
        """Use a normal click only when the target is visibly uncovered."""
        try:
            WebDriverWait(self.driver, 8).until(
                lambda driver: driver.execute_script("""
                    const e = arguments[0];
                    e.scrollIntoView({block: 'center', inline: 'center'});
                    const r = e.getBoundingClientRect();
                    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                    return !!top && (top === e || e.contains(top));
                """, element)
            )
            element.click()
        except (TimeoutException, WebDriverException) as exc:
            raise IndexRequestError(
                "다른 화면 요소가 요청 버튼을 가리고 있습니다. Search Console의 열린 안내창을 닫고 다시 시도하세요."
            ) from exc

    def _capture(self, url):
        try:
            folder = self.artifact_root / "screenshots"
            folder.mkdir(parents=True, exist_ok=True)
            name = re.sub(r"[^a-zA-Z0-9_-]", "_", url[-80:])
            self.driver.save_screenshot(str(folder / f"error_{name}.png"))
        except Exception:
            self.log.exception("Screenshot save failed")

    def close(self):
        if self.driver:
            try:
                # Detach without closing the user's Chrome session.
                self.driver.service.stop()
            except Exception:
                self.log.exception("ChromeDriver detach failed")
            self.driver = None
