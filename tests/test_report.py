import tempfile
import unittest
from pathlib import Path

from reports.html_report import generate_run_report
from storage.history import HistoryStore


class ReportTests(unittest.TestCase):
    def test_completed_run_can_be_rebuilt_from_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = HistoryStore(root / "history.sqlite3")
            url = "https://example.com/post"
            run_id = store.start_run([url], "https://example.com/")
            store.record_inspection(url, "INDEXED", "URL is on Google")
            store.mark_url(run_id, url, "DONE")
            store.finish_run(run_id, "DONE")

            latest = store.latest_reportable_run()
            self.assertEqual(latest, (run_id, "https://example.com/"))
            path = generate_run_report(store, latest[0], latest[1], root / "reports")
            self.assertTrue(path.is_file())
            self.assertIn(url, path.read_text(encoding="utf-8"))
            self.assertEqual(path, generate_run_report(store, latest[0], latest[1], root / "reports"))
            store.close()


if __name__ == "__main__":
    unittest.main()
