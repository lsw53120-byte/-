import tempfile
import threading
import unittest
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import Mock

from gui.main_window import App


class GuiEventTests(unittest.TestCase):
    def test_completed_report_is_shown_after_worker_events(self):
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / "report.html"
            report.write_text("<html></html>", encoding="utf-8")
            events = Queue()
            events.put("malformed event")
            events.put(("report_ready", str(report)))
            events.put(("finished", "작업을 마쳤습니다."))
            view = SimpleNamespace(
                events=events, logger=Mock(), report_button=Mock(), report_path_label=Mock(),
                stop_event=threading.Event(), current_report_ready=False, last_report=None,
                _log=Mock(), _finish_activity=Mock(), _complete=Mock(), open_report=Mock(),
                activity_since=None, after=Mock(), _poll=Mock(),
            )

            App._poll(view)

            self.assertEqual(view.last_report, report)
            view.report_button.configure.assert_called_with(state="normal")
            view._finish_activity.assert_called_with("진단 완료")
            view.open_report.assert_called_once_with()
            view.after.assert_called_once_with(100, view._poll)


if __name__ == "__main__":
    unittest.main()
