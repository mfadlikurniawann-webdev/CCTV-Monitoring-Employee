import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, camera TEXT NOT NULL, track INTEGER NOT NULL,
                    zone TEXT NOT NULL, recorded_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    start_seconds REAL NOT NULL, end_seconds REAL NOT NULL,
                    duration REAL NOT NULL, status TEXT NOT NULL,
                    review TEXT NOT NULL DEFAULT 'pending', snapshot TEXT);
                CREATE INDEX IF NOT EXISTS events_recorded ON events(recorded_at);
            ''')
            # A previous unclean exit must not leave events marked active indefinitely.
            con.execute("UPDATE events SET status='interrupted' WHERE status='active'")

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        try:
            with con:
                yield con
        finally:
            con.close()

    def start(self, camera, track, state, snapshot=None):
        with self.connect() as con:
            cursor = con.execute('''INSERT INTO events
                (camera,track,zone,recorded_at,updated_at,start_seconds,end_seconds,duration,status,snapshot)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (camera, track, state.zone, utcnow(), utcnow(), state.start, state.last,
                 state.last - state.start, 'active', snapshot))
            return cursor.lastrowid

    def update(self, event_id, state, status):
        with self.connect() as con:
            con.execute('UPDATE events SET end_seconds=?,duration=?,status=?,updated_at=? WHERE id=?',
                        (state.last, state.last - state.start, status, utcnow(), event_id))

    def list(self, limit=100):
        with self.connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,))]

    def review(self, event_id, value):
        with self.connect() as con:
            return con.execute('UPDATE events SET review=? WHERE id=?', (value, event_id)).rowcount > 0

    def purge(self, days, snapshot_dir):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.connect() as con:
            names = [r[0] for r in con.execute('SELECT snapshot FROM events WHERE recorded_at < ?', (cutoff,))]
            con.execute('DELETE FROM events WHERE recorded_at < ?', (cutoff,))
        for name in names:
            if name and Path(name).name == name:
                (Path(snapshot_dir) / name).unlink(missing_ok=True)
