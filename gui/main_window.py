import logging
import os
import queue
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import customtkinter as ctk
from tkinter import filedialog, messagebox
from automation.collector import MATNAM_HOST, collect
from automation.chrome_launcher import open_connected_chrome
from automation.worker import AutomationWorker
from core.url_normalizer import is_in_property
from reports.html_report import generate_run_report
from storage.history import HistoryStore
from storage.settings import load_settings, save_settings
from utils.logger import configure

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self, data_dir=None):
        super().__init__()
        self.title("블로그 검색노출 진단·색인요청 도우미")
        self.geometry("850x850")
        self.minsize(720, 680)
        self.root = Path(data_dir) if data_dir else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "SearchConsoleTool"
        for name in ("data", "logs", "reports", "screenshots", "chrome_profile"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.logger = configure(self.root)
        self.store = HistoryStore(self.root / "data" / "history.sqlite3")
        self.settings = load_settings(self.root)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="search-console")
        self.collector_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="url-collector")
        self.run_id = None
        self.last_report = None
        self.recovered_report = False
        self.current_report_ready = False
        self.future = None
        self.results = []
        try:
            latest = self.store.latest_reportable_run()
            if latest:
                expected = self.root / "reports" / f"서치콘솔_진단보고서_작업{latest[0]}.html"
                self.recovered_report = not expected.is_file()
                self.last_report = generate_run_report(
                    self.store, latest[0], latest[1], self.root / "reports")
        except Exception:
            self.logger.exception("Could not restore the latest report")
        self.activity_text = "준비 완료"
        self.activity_since = None
        self.completed_count = 0
        self.total_count = 0
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._poll)
        if self.recovered_report and self.last_report:
            self.after(500, self.open_report)

    def _build(self):
        ctk.CTkLabel(self, text="블로그 검색노출 진단·색인요청 도우미", font=ctk.CTkFont(size=24, weight="bold")).pack(anchor="w", padx=22, pady=(18, 2))
        ctk.CTkLabel(self, text="URL 상태를 진단하고 조건에 맞을 때만 Google에 재크롤링 검토를 요청합니다.",
                     text_color="gray").pack(anchor="w", padx=22, pady=(0, 10))
        card = ctk.CTkFrame(self)
        card.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(card, text="Search Console 속성 주소 (예: https://example.com/ 또는 sc-domain:example.com)").pack(anchor="w", padx=12, pady=(10, 2))
        self.property_entry = ctk.CTkEntry(card, placeholder_text="https://example.com/")
        self.property_entry.pack(fill="x", padx=12, pady=(0, 8))
        if self.settings.property_url:
            self.property_entry.insert(0, self.settings.property_url)
        ctk.CTkLabel(card, text="matnam 사이트만 지원합니다. 사이트 주소는 전체 글 색인, 글 주소는 개별 색인입니다.").pack(anchor="w", padx=12, pady=(3, 2))
        self.input = ctk.CTkTextbox(card, height=115)
        self.input.pack(fill="x", padx=12, pady=(0, 8))
        self.input.insert("1.0", "https://")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkLabel(row, text="최대 URL").pack(side="left")
        self.max_urls = ctk.CTkEntry(row, width=70)
        self.max_urls.insert(0, str(self.settings.max_urls))
        self.max_urls.pack(side="left", padx=(6, 16))
        ctk.CTkLabel(row, text="일일 요청 한도").pack(side="left")
        self.daily_limit = ctk.CTkEntry(row, width=70)
        self.daily_limit.insert(0, str(self.settings.daily_request_limit))
        self.daily_limit.pack(side="left", padx=6)
        self.auto_request = ctk.CTkCheckBox(row, text="정책에 맞는 URL 색인 요청 허용 (기본 꺼짐)")
        if self.settings.auto_request:
            self.auto_request.select()
        self.auto_request.pack(side="left", padx=8)
        schedule = ctk.CTkFrame(card, fg_color="transparent")
        schedule.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkLabel(schedule, text="색인 요청 재시도 대기(일)").pack(side="left")
        self.cooldown_days = ctk.CTkEntry(schedule, width=55)
        self.cooldown_days.insert(0, str(self.settings.request_cooldown_days))
        self.cooldown_days.pack(side="left", padx=5)
        ctk.CTkLabel(card, text="로그인한 원격 디버깅 Chrome이 있으면 그 창에 연결합니다. 없으면 도구의 기존 Chrome 로그인 프로필을 엽니다.",
                     text_color="gray", wraplength=780).pack(anchor="w", padx=12, pady=(0, 4))
        self.browser_button = ctk.CTkButton(card, text="로그인 브라우저 열기 / 연결 준비",
                                            command=self.open_login_browser)
        self.browser_button.pack(anchor="w", padx=12, pady=(0, 10))
        profile_row = ctk.CTkFrame(card, fg_color="transparent")
        profile_row.pack(fill="x", padx=12, pady=(0, 10))
        self.profile_path_label = ctk.CTkLabel(
            profile_row,
            text=self.settings.chrome_profile_path or str(self.root / "chrome_profile"),
            text_color="gray",
            anchor="w",
        )
        self.profile_path_label.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(profile_row, text="기존 로그인 프로필 폴더 선택", width=190,
                      command=self.choose_chrome_profile).pack(side="right")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=18, pady=4)
        self.start_button = ctk.CTkButton(buttons, text="URL 가져오기 및 진단 시작", command=self.start)
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.resume_button = ctk.CTkButton(buttons, text="중단 작업 이어하기", command=self.resume)
        self.resume_button.pack(side="left", padx=6)
        self.stop_button = ctk.CTkButton(buttons, text="안전 중지", command=self.stop, state="disabled", fg_color="#b42318")
        self.stop_button.pack(side="left", padx=6)
        self.report_button = ctk.CTkButton(buttons, text="보고서 열기", command=self.open_report,
                                           state="normal" if self.last_report else "disabled")
        self.report_button.pack(side="left", padx=(6, 0))
        self.folder_button = ctk.CTkButton(buttons, text="결과 폴더", command=self.open_folder)
        self.folder_button.pack(side="left", padx=(6, 0))
        self.progress = ctk.CTkProgressBar(self)
        self.progress.pack(fill="x", padx=20, pady=(8, 3))
        self.progress.set(0)
        self.status_label = ctk.CTkLabel(self, text="준비 완료", wraplength=800, anchor="w", justify="left")
        self.status_label.pack(anchor="w", padx=22)
        self.count_label = ctk.CTkLabel(self, text="검사 대기", text_color="gray")
        self.count_label.pack(anchor="w", padx=22)
        self.report_path_label = ctk.CTkLabel(
            self, text=f"보고서: {self.last_report}" if self.last_report else "보고서: 아직 생성되지 않음",
            text_color="gray", wraplength=800, anchor="w", justify="left")
        self.report_path_label.pack(anchor="w", padx=22)
        self.logbox = ctk.CTkTextbox(self, height=370, font=ctk.CTkFont(family="Consolas", size=12))
        self.logbox.pack(fill="both", expand=True, padx=18, pady=(4, 14))
        ctk.CTkLabel(self, text=f"데이터와 연결 Chrome 프로필 저장 위치: {self.root}", text_color="gray",
                     wraplength=810).pack(anchor="w", padx=20, pady=(0, 8))

    def _read_settings(self):
        settings = self.settings
        settings.property_url = self.property_entry.get().strip()
        settings.max_urls = int(self.max_urls.get())
        settings.daily_request_limit = int(self.daily_limit.get())
        settings.request_cooldown_days = int(self.cooldown_days.get())
        settings.auto_request = bool(self.auto_request.get())
        settings.validate()
        if not settings.property_url:
            raise ValueError("Search Console 속성 주소를 입력하세요.")
        if settings.auto_request:
            approved = messagebox.askyesno(
                "색인 요청 기능 확인",
                "이 기능은 Google에 재크롤링 검토를 요청할 뿐 색인 완료·검색 노출·순위를 보장하지 않습니다.\n\n"
                "소수의 본인 소유 URL에만 사용하고, Google이 표시하는 한도와 안내를 따라야 합니다. 계속할까요?",
                parent=self,
            )
            if not approved:
                raise ValueError("사용자가 색인 요청 기능을 취소했습니다.")
        save_settings(self.root, settings)
        return settings

    def start(self):
        try:
            settings = self._read_settings()
            source = self.input.get("1.0", "end").strip()
            if not source or source == "https://":
                raise ValueError("사이트 주소, 사이트맵 또는 검사할 URL을 입력하세요.")
            self.stop_event.clear()
            self.start_button.configure(state="disabled")
            self.resume_button.configure(state="disabled")
            self.browser_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.progress.set(0)
            self.completed_count = self.total_count = 0
            self.count_label.configure(text="URL 수집 중")
            self._set_activity("사이트맵 또는 URL을 읽는 중입니다.", animate=True)
            self._log("입력 URL을 가져오는 중입니다.")
            progress = lambda message, count: self.events.put(("collect_status", (message, count)))
            self.future = self.collector_pool.submit(
                collect, source, settings.max_urls, self.stop_event, progress, MATNAM_HOST)
            self.future.add_done_callback(lambda future: self.events.put(("collected", (future, settings))))
        except Exception as exc:
            self._finish_activity("시작할 수 없습니다.")
            messagebox.showerror("입력 확인", str(exc))
            self._complete()

    def open_login_browser(self):
        self.browser_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.resume_button.configure(state="disabled")
        self._set_activity("로그인 Chrome 연결을 준비하고 있습니다.", animate=True)
        profile = Path(self.settings.chrome_profile_path) if self.settings.chrome_profile_path else self.root / "chrome_profile"
        self.future = self.collector_pool.submit(open_connected_chrome, profile)
        self.future.add_done_callback(lambda future: self.events.put(("browser_opened", future)))

    def choose_chrome_profile(self):
        current = self.settings.chrome_profile_path or str(self.root / "chrome_profile")
        selected = filedialog.askdirectory(
            parent=self,
            title="기존 자동화 Chrome 프로필 폴더 선택",
            initialdir=current if Path(current).is_dir() else str(self.root),
        )
        if not selected:
            return
        self.settings.chrome_profile_path = str(Path(selected))
        try:
            self.settings.validate()
            save_settings(self.root, self.settings)
            self.profile_path_label.configure(text=self.settings.chrome_profile_path)
            self._log("Chrome 프로필 경로를 저장했습니다.")
        except Exception as exc:
            messagebox.showerror("프로필 경로 오류", str(exc))

    def _handle_collected(self, future, settings):
        try:
            _, urls = future.result()
            if self.stop_event.is_set():
                self._log("URL 수집을 중지했습니다.")
                self._finish_activity("URL 수집 중지됨")
                self._complete()
                return
            if not urls:
                raise ValueError("검사할 URL을 찾지 못했습니다.")
            self._log(f"검사할 URL {len(urls)}개를 찾았습니다.")
            self.count_label.configure(text=f"URL 수집 완료: {len(urls)}개")
            invalid = [url for url in urls if not is_in_property(url, settings.property_url)]
            if invalid:
                raise ValueError(f"입력 URL이 지정한 Search Console 속성 범위 밖입니다: {invalid[0]}")
            run_id = self.store.start_run(urls, settings.property_url)
            self._launch(run_id, settings)
        except Exception as exc:
            self._log(f"URL 수집 또는 입력 확인 실패: {exc}")
            self._finish_activity("URL 수집 실패")
            messagebox.showerror("입력 확인", str(exc))
            self._complete()

    def resume(self):
        try:
            settings = self._read_settings()
            run_id = self.store.resumable_run(settings.property_url)
            if not run_id:
                messagebox.showinfo("안내", "이어서 처리할 미완료 URL이 없습니다.")
                return
            self._launch(run_id, settings)
        except Exception as exc:
            self._finish_activity("이어갈 수 없습니다.")
            messagebox.showerror("재개할 수 없습니다", str(exc))

    def _launch(self, run_id, settings):
        self.run_id = run_id
        self.stop_event.clear()
        self.start_button.configure(state="disabled")
        self.resume_button.configure(state="disabled")
        self.browser_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.current_report_ready = False
        self.results = []
        self.completed_count = self.total_count = 0
        self.progress.set(0)
        self.count_label.configure(text="진단 준비 중")
        self._set_activity("로그인 Chrome 연결을 준비합니다.", animate=True)
        worker = AutomationWorker(self.root, settings, self._queue_worker_event, self.stop_event)
        self.future = self.pool.submit(worker.run, run_id)
        self.future.add_done_callback(self._worker_done)

    def _queue_worker_event(self, kind, payload):
        self.events.put((kind, payload))

    def _worker_done(self, future):
        try:
            error = future.exception()
        except Exception:
            return
        if error:
            self.events.put(("error", f"백그라운드 작업 종료 오류: {error}"))

    def stop(self):
        self.stop_event.set()
        self._set_activity("중지 요청됨 · 현재 URL 수집 또는 검사가 끝나면 멈춥니다.")

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if not isinstance(event, tuple) or len(event) != 2:
                    self.logger.error("Ignored malformed UI event: %r", event)
                    continue
                kind, payload = event
                if kind == "log":
                    self._log(payload)
                elif kind == "collect_status":
                    message, count = payload
                    if not self.stop_event.is_set():
                        self._set_activity(message, animate=True)
                    self.count_label.configure(text=f"찾은 URL: {count}개" if count else "URL 수집 중")
                elif kind == "phase":
                    if not self.stop_event.is_set():
                        self._set_activity(payload, animate=self.total_count == 0)
                elif kind == "collected":
                    future, settings = payload
                    self._handle_collected(future, settings)
                elif kind == "browser_opened":
                    future = payload
                    try:
                        _, browser_message = future.result()
                        self._log(browser_message)
                        self._finish_activity("Chrome 연결 준비 완료")
                    except Exception as exc:
                        self._log(f"Chrome 연결 준비 실패: {exc}")
                        messagebox.showerror("Chrome 연결 실패", str(exc))
                        self._finish_activity("Chrome 연결 실패")
                    finally:
                        self.browser_button.configure(state="normal")
                        self._complete()
                elif kind == "progress":
                    done, total, url = payload
                    self.progress.stop()
                    self.progress.configure(mode="determinate")
                    self.progress.set(done / max(1, total))
                    self.completed_count, self.total_count = done, total
                    self.count_label.configure(text=f"처리 완료: {done}/{total}개")
                elif kind == "result":
                    self.results.append(payload)
                    self._log(f"{payload['status_code']} · {payload['action_taken']} · {payload['url']}")
                elif kind == "report_ready":
                    self.last_report = Path(payload)
                    self.current_report_ready = True
                    self.report_button.configure(state="normal")
                    self.report_path_label.configure(text=f"보고서: {self.last_report}")
                    self._log(f"보고서 저장 완료: {self.last_report}")
                elif kind == "report_error":
                    self._log(f"보고서 생성 실패: {payload}")
                elif kind == "login":
                    self._log(payload)
                    self._finish_activity("로그인 또는 사용자 확인이 필요합니다.")
                    self._complete()
                elif kind in ("finished", "error"):
                    self._log(payload)
                    if kind == "error":
                        self._finish_activity("오류로 중지됨")
                    elif self.stop_event.is_set():
                        self._finish_activity("중지됨 · 남은 URL은 이어서 처리할 수 있습니다.")
                    else:
                        self._finish_activity("진단 완료")
                    self._complete()
                    if kind == "finished" and not self.stop_event.is_set() and self.current_report_ready:
                        self.open_report()
        except queue.Empty:
            pass
        except Exception as exc:
            self.logger.exception("GUI event handling failed")
            self._finish_activity("화면 갱신 오류 · 로그를 확인하세요.")
            self._complete()
            self.logger.error("GUI event handling failed: %s", exc)
        if self.activity_since is not None:
            elapsed = int(time.monotonic() - self.activity_since)
            self.status_label.configure(text=f"{self.activity_text} · 경과 {elapsed // 60:02d}:{elapsed % 60:02d}")
        self.after(100, self._poll)

    def _complete(self):
        self.progress.stop()
        self.activity_since = None
        self.start_button.configure(state="normal")
        self.resume_button.configure(state="normal")
        self.browser_button.configure(state="normal")
        self.stop_button.configure(state="disabled")

    def _set_activity(self, message, animate=False):
        self.activity_text = message
        self.activity_since = time.monotonic()
        self.status_label.configure(text=f"{message} · 경과 00:00")
        if animate:
            self.progress.configure(mode="indeterminate")
            self.progress.start()

    def _finish_activity(self, message):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.activity_since = None
        self.activity_text = message
        self.status_label.configure(text=message)

    def _log(self, message):
        self.logbox.insert("end", f"[{datetime.now():%H:%M:%S}] {message}\n")
        self.logbox.see("end")
        self.logger.info("%s", message)

    def open_report(self):
        if not self.last_report or not self.last_report.exists():
            messagebox.showinfo("보고서 없음", "아직 저장된 보고서가 없습니다.")
            return
        try:
            os.startfile(str(self.last_report))
        except (AttributeError, OSError):
            if not webbrowser.open(self.last_report.as_uri()):
                messagebox.showerror("보고서를 열 수 없습니다", str(self.last_report))

    def open_folder(self):
        try:
            os.startfile(str(self.root))
        except (AttributeError, OSError) as exc:
            messagebox.showerror("폴더를 열 수 없습니다", str(exc))

    def _close(self):
        if self.future and not self.future.done():
            self.stop_event.set()
            self.status_label.configure(text="브라우저 작업을 안전하게 마친 뒤 종료합니다.")
            self.after(250, self._finish_close)
            return
        self._finish_close()

    def _finish_close(self):
        if self.future and not self.future.done():
            self.after(250, self._finish_close)
            return
        try:
            self.store.close()
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.collector_pool.shutdown(wait=False, cancel_futures=True)
        finally:
            self.destroy()

