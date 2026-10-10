import logging
import time
from pathlib import Path
from core.indexing_policy import ADVICE, request_decision
from core.models import Status
from automation.search_console import SearchConsole
from automation.chrome_launcher import open_connected_chrome
from storage.history import HistoryStore
from reports.html_report import generate_run_report
from utils.exceptions import LoginRequiredError, IndexRequestError, SearchConsoleTimeout


class AutomationWorker:
    def __init__(self, root, settings, emit, stop_event):
        self.root, self.settings = root, settings
        self.store_path = root / "data" / "history.sqlite3"
        self.emit, self.stop = emit, stop_event
        self.log = logging.getLogger("search_console")
        self.browser = SearchConsole(root, settings.timeout_seconds, self.log)

    def run(self, run_id):
        # Keep each SQLite connection on the thread that owns it.
        self.store = HistoryStore(self.store_path)
        urls = self.store.pending(run_id)
        if not urls:
            self.store.finish_run(run_id, "DONE")
            self._publish_report(run_id)
            self.emit("finished", "이미 처리할 URL이 없습니다.")
            self.store.close()
            return
        try:
            if self.stop.is_set():
                self.store.finish_run(run_id, "STOPPED")
                self._publish_report(run_id)
                self.emit("finished", "중지했습니다. 남은 URL은 다음 실행에서 이어갈 수 있습니다.")
                return
            profile = self.settings.chrome_profile_path
            profile = Path(profile) if profile else self.root / "chrome_profile"
            self.emit("phase", "로그인 Chrome을 연결하는 중입니다.")
            self.emit("log", "로그인 Chrome 연결을 준비합니다.")
            debug_port, browser_message = open_connected_chrome(profile)
            self.emit("log", browser_message)
            if self.stop.is_set():
                self.store.finish_run(run_id, "STOPPED")
                self._publish_report(run_id)
                self.emit("finished", "중지했습니다. 남은 URL은 다음 실행에서 이어갈 수 있습니다.")
                return
            self.browser.start(debug_port)
            self.emit("phase", "Search Console에서 URL을 검사하는 중입니다.")
            self.emit("log", "연결된 Chrome의 로그인 상태와 Search Console 속성을 확인합니다.")
            for number, url in enumerate(urls, 1):
                if self.stop.is_set():
                    self.store.finish_run(run_id, "STOPPED")
                    break
                self.emit("progress", (number - 1, len(urls), url))
                self.emit("phase", f"URL 검사 중 ({number}/{len(urls)}): {url}")
                inspection, error = None, None
                for attempt in range(self.settings.retries + 1):
                    if self.stop.is_set():
                        break
                    try:
                        inspection = self.browser.inspect(url)
                        error = None
                        break
                    except LoginRequiredError:
                        self.store.finish_run(run_id, "PAUSED")
                        self._publish_report(run_id)
                        self.emit("login", "연결된 Chrome에서 Google 로그인과 속성을 확인한 뒤 이어서 실행하세요.")
                        return
                    except SearchConsoleTimeout as exc:
                        error = str(exc)
                    except Exception as exc:
                        error = str(exc)
                    if attempt < self.settings.retries and not self.stop.is_set():
                        self.log.warning("Retry %s/%s for %s: %s", attempt + 1, self.settings.retries, url, error)
                        self.emit("phase", f"URL 검사 재시도 중 ({number}/{len(urls)}, {attempt + 2}회): {url}")
                        time.sleep(min(2 ** attempt, 5))
                if self.stop.is_set():
                    self.store.finish_run(run_id, "STOPPED")
                    break
                status = inspection.status if inspection else Status.TIMEOUT

                raw = inspection.raw if inspection else ""
                canonical = inspection.canonical_url if inspection else None
                self.store.record_inspection(url, status.value, raw, canonical, error)
                blocked = any(token in raw.lower() for token in ("quota", "limit exceeded", "할당량", "요청 한도"))
                latest = self.store.latest_request(url)
                can_request, reason = request_decision(
                    status, self.settings, latest, self.store.requests_today(), blocked)
                action = "요청 안 함"
                if can_request and not self.stop.is_set():
                    self.emit("phase", f"색인 요청 확인 중 ({number}/{len(urls)}): {url}")
                    # Persist intent before UI interaction. Ambiguous outcomes are never blindly retried.
                    self.store.log_request(url, "ATTEMPTED", reason)
                    try:
                        action = self.browser.request_indexing(url)
                        self.store.log_request(url, "CONFIRMED", action)
                    except IndexRequestError as exc:
                        action = "요청 결과 확인 필요"
                        self.store.log_request(url, "UNKNOWN", str(exc))
                        self.log.warning("Index request result uncertain for %s: %s", url, exc)
                    except Exception as exc:
                        action = "요청 결과 확인 필요"
                        self.store.log_request(url, "UNKNOWN", str(exc))
                        self.log.exception("Unexpected request UI error for %s", url)
                result = {
                    "url": url, "status_code": status.value, "status_title": status.value,
                    "summary": reason, "root_cause": error or ADVICE[status],
                    "action_guide": [ADVICE[status]], "action_taken": action,
                    "canonical_url": canonical, "raw_status": raw, "last_checked": self.store.get(url)["last_checked"],
                }
                self.store.mark_url(run_id, url, "DONE")
                self.emit("result", result)
                self.emit("progress", (number, len(urls), url))
                if status == Status.TEMP_ERROR and blocked:
                    self.store.finish_run(run_id, "PAUSED")
                    self._publish_report(run_id)
                    self.emit("login", "Search Console에서 요청 한도/확인 화면이 보여 작업을 멈췄습니다.")
                    return
            if self.stop.is_set():
                self.store.finish_run(run_id, "STOPPED")
                self._publish_report(run_id)
                self.emit("finished", "중지했습니다. 남은 URL은 다음 실행에서 이어갈 수 있습니다.")
            else:
                self.store.finish_run(run_id, "DONE")
                self._publish_report(run_id)
                self.emit("finished", "작업을 마쳤습니다.")
        except LoginRequiredError as exc:
            self.store.finish_run(run_id, "PAUSED")
            self._publish_report(run_id)
            self.emit("login", str(exc))
        except Exception as exc:
            self.log.exception("Automation run failed")
            self.store.finish_run(run_id, "STOPPED")
            self._publish_report(run_id)
            self.emit("error", str(exc))
        finally:
            self.browser.close()
            self.store.close()

    def _publish_report(self, run_id):
        try:
            path = generate_run_report(self.store, run_id, self.settings.property_url,
                                       self.root / "reports")
            if path is not None:
                self.emit("report_ready", str(path))
        except Exception as exc:
            self.log.exception("Report generation failed")
            self.emit("report_error", str(exc))

