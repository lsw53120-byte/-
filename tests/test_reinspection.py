import tempfile
import threading
import unittest
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import patch

from automation.worker import AutomationWorker
from core.models import Inspection, Settings, Status
from gui.main_window import App
from storage.history import HistoryStore


class ReinspectionTests(unittest.TestCase):
    def test_new_run_inspects_url_even_when_checked_recently(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "data" / "history.sqlite3"
            url = "https://example.com/post"
            store = HistoryStore(path)
            old_run = store.start_run([url], "https://example.com/")
            store.record_inspection(url, Status.INDEXED.value, "URL is on Google")
            store.mark_url(old_run, url, "DONE")
            store.finish_run(old_run, "DONE")
            new_run = store.start_run([url], "https://example.com/")
            store.close()

            settings = Settings(property_url="https://example.com/")
            events = Queue()
            sink = SimpleNamespace(events=events)
            with patch("automation.worker.open_connected_chrome", return_value=(54321, "Chrome ready")), \
                    patch("automation.worker.SearchConsole") as browser_type:
                browser_type.return_value.inspect.return_value = Inspection(
                    status=Status.INDEXED, raw="URL is on Google")
                worker = AutomationWorker(root, settings, App._queue_worker_event.__get__(sink),
                                          threading.Event())
                worker.run(new_run)
                browser_type.return_value.start.assert_called_once_with(54321)
                browser_type.return_value.inspect.assert_called_once_with(url)

            store = HistoryStore(path)
            self.assertEqual(store.pending(new_run), [])
            self.assertEqual(store.latest_reportable_run()[0], new_run)
            kinds = []
            while not events.empty():
                event = events.get_nowait()
                self.assertEqual(len(event), 2)
                kinds.append(event[0])
            self.assertLess(kinds.index("report_ready"), kinds.index("finished"))
            store.close()


if __name__ == "__main__":
    unittest.main()
