import json
import sqlite3
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from core.models import now_iso


class HistoryStore:
    """SQLite URL state, per-request audit log, and resumable run queue."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS urls(
          url TEXT PRIMARY KEY, first_seen TEXT NOT NULL, last_checked TEXT,
          last_status TEXT, canonical_url TEXT, raw_status TEXT, last_error TEXT,
          retry_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS requests(
          id INTEGER PRIMARY KEY, url TEXT NOT NULL, attempted_at TEXT NOT NULL,
          outcome TEXT NOT NULL, detail TEXT
        );
        CREATE TABLE IF NOT EXISTS runs(
          id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          state TEXT NOT NULL, property_url TEXT
        );
        CREATE TABLE IF NOT EXISTS run_urls(
          run_id INTEGER NOT NULL, url TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
          PRIMARY KEY(run_id,url), FOREIGN KEY(run_id) REFERENCES runs(id)
        );
        """)
        self.db.commit()

    def get(self, url):
        row = self.db.execute("SELECT * FROM urls WHERE url=?", (url,)).fetchone()
        return dict(row) if row else None

    def record_inspection(self, url, status, raw="", canonical=None, error=None):
        existing = self.get(url)
        first_seen = existing["first_seen"] if existing else now_iso()
        retries = (existing["retry_count"] if existing else 0) + (1 if error else 0)
        self.db.execute("""INSERT INTO urls(url,first_seen,last_checked,last_status,canonical_url,raw_status,last_error,retry_count)
          VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET last_checked=excluded.last_checked,
          last_status=excluded.last_status,canonical_url=excluded.canonical_url,raw_status=excluded.raw_status,
          last_error=excluded.last_error,retry_count=excluded.retry_count""",
          (url, first_seen, now_iso(), status, canonical, raw[:4000], error, retries))
        self.db.commit()

    def latest_request(self, url):
        row = self.db.execute("SELECT attempted_at FROM requests WHERE url=? ORDER BY id DESC LIMIT 1", (url,)).fetchone()
        return row[0] if row else None

    def requests_today(self):
        local_now = datetime.now().astimezone()
        local_start = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
        local_end = local_start + timedelta(days=1)
        start_utc = local_start.astimezone(timezone.utc).isoformat(timespec="seconds")
        end_utc = local_end.astimezone(timezone.utc).isoformat(timespec="seconds")
        return self.db.execute("SELECT COUNT(*) FROM requests WHERE attempted_at>=? AND attempted_at<? AND outcome='ATTEMPTED'",
                               (start_utc, end_utc)).fetchone()[0]

    def request_summary(self, url):
        row = self.db.execute("SELECT outcome,attempted_at,detail FROM requests WHERE url=? ORDER BY id DESC LIMIT 1", (url,)).fetchone()
        return dict(row) if row else None

    def log_request(self, url, outcome, detail=""):
        self.db.execute("INSERT INTO requests(url,attempted_at,outcome,detail) VALUES(?,?,?,?)",
                        (url, now_iso(), outcome, detail[:1000]))
        self.db.commit()

    def start_run(self, urls, property_url):
        now = now_iso()
        cur = self.db.execute("INSERT INTO runs(started_at,updated_at,state,property_url) VALUES(?,?,?,?)",
                              (now, now, "RUNNING", property_url))
        run_id = cur.lastrowid
        self.db.executemany("INSERT INTO run_urls(run_id,url) VALUES(?,?)", [(run_id, u) for u in urls])
        self.db.commit()
        return run_id

    def pending(self, run_id):
        return [x[0] for x in self.db.execute("SELECT url FROM run_urls WHERE run_id=? AND state='PENDING' ORDER BY rowid", (run_id,))]

    def resumable_run(self, property_url):
        row = self.db.execute("SELECT id FROM runs WHERE property_url=? AND state IN ('RUNNING','STOPPED','PAUSED') ORDER BY id DESC LIMIT 1",
                              (property_url,)).fetchone()
        return row[0] if row else None

    def run_results(self, run_id):
        rows = self.db.execute("""SELECT u.* FROM run_urls q JOIN urls u ON u.url=q.url
          WHERE q.run_id=? AND q.state='DONE' ORDER BY q.rowid""", (run_id,)).fetchall()
        return [dict(row) for row in rows]

    def latest_reportable_run(self):
        row = self.db.execute("""SELECT r.id, r.property_url FROM runs r
          WHERE EXISTS (SELECT 1 FROM run_urls q WHERE q.run_id=r.id AND q.state='DONE')
          ORDER BY r.id DESC LIMIT 1""").fetchone()
        return (row[0], row[1]) if row else None

    def mark_url(self, run_id, url, state):
        self.db.execute("UPDATE run_urls SET state=? WHERE run_id=? AND url=?", (state, run_id, url))
        self.db.execute("UPDATE runs SET updated_at=? WHERE id=?", (now_iso(), run_id))
        self.db.commit()

    def finish_run(self, run_id, state):
        self.db.execute("UPDATE runs SET state=?,updated_at=? WHERE id=?", (state, now_iso(), run_id))
        self.db.commit()

    def close(self):
        self.db.close()


def migrate_legacy_json(source: Path, store: HistoryStore):
    """Import date -> URL[] legacy history without deleting or modifying the source."""
    raw = json.loads(source.read_text(encoding="utf-8"))
    imported = 0
    for date, urls in raw.items():
        for url in urls if isinstance(urls, list) else []:
            existing = store.get(url)
            if existing and existing.get("last_checked", "") >= date:
                continue
            old_time = date + "T00:00:00+00:00"
            store.db.execute("""INSERT INTO urls(url,first_seen,last_checked,last_status,raw_status)
              VALUES(?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET last_checked=excluded.last_checked,
              last_status=excluded.last_status,raw_status=excluded.raw_status""",
              (url, date, old_time, "UNKNOWN", "Legacy history only recorded that URL was processed; inspection status is unknown."))
            imported += 1
    store.db.commit()
    return imported
