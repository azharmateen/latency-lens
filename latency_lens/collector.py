"""
Trace data collector: stores request traces in a local SQLite database.
"""

import sqlite3
import time
import threading
from datetime import datetime, timezone
from pathlib import Path


class TraceCollector:
    """Collects and stores trace data in SQLite."""

    def __init__(self, db_path: str = "./latency_lens.db"):
        self.db_path = db_path
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def init_db(self):
        """Create the traces table if it doesn't exist."""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT NOT NULL,
                method TEXT NOT NULL DEFAULT 'GET',
                status_code INTEGER NOT NULL DEFAULT 200,
                duration_ms REAL NOT NULL,
                request_size INTEGER DEFAULT 0,
                response_size INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL,
                ts_epoch REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_endpoint ON traces(endpoint)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_ts ON traces(ts_epoch)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status_code)")
        conn.commit()

    def record(
        self,
        endpoint: str,
        method: str = "GET",
        status_code: int = 200,
        duration_ms: float = 0.0,
        request_size: int = 0,
        response_size: int = 0,
    ):
        """Record a single request trace."""
        now = datetime.now(timezone.utc)
        ts_epoch = now.timestamp()
        timestamp = now.isoformat()

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO traces
               (endpoint, method, status_code, duration_ms, request_size, response_size, timestamp, ts_epoch)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (endpoint, method, status_code, duration_ms, request_size, response_size, timestamp, ts_epoch),
        )
        conn.commit()

    def query_traces(self, hours: int = 24, endpoint: str = None, limit: int = 10000) -> list[dict]:
        """Query traces within a time window."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row

        cutoff = time.time() - (hours * 3600)
        params: list = [cutoff]

        sql = "SELECT * FROM traces WHERE ts_epoch >= ?"
        if endpoint:
            sql += " AND endpoint = ?"
            params.append(endpoint)
        sql += f" ORDER BY ts_epoch DESC LIMIT {limit}"

        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_endpoints(self, hours: int = 24) -> list[str]:
        """Get unique endpoints within a time window."""
        conn = self._get_conn()
        cutoff = time.time() - (hours * 3600)
        cursor = conn.execute(
            "SELECT DISTINCT endpoint FROM traces WHERE ts_epoch >= ? ORDER BY endpoint",
            (cutoff,),
        )
        return [row[0] for row in cursor.fetchall()]

    def get_endpoint_stats(self, endpoint: str, hours: int = 24) -> dict:
        """Get aggregate stats for a specific endpoint."""
        conn = self._get_conn()
        cutoff = time.time() - (hours * 3600)

        cursor = conn.execute(
            """SELECT
                COUNT(*) as count,
                AVG(duration_ms) as avg_ms,
                MIN(duration_ms) as min_ms,
                MAX(duration_ms) as max_ms,
                AVG(request_size) as avg_req_size,
                AVG(response_size) as avg_resp_size
               FROM traces
               WHERE endpoint = ? AND ts_epoch >= ?""",
            (endpoint, cutoff),
        )
        row = cursor.fetchone()

        if not row or row[0] == 0:
            return {"count": 0}

        # Calculate percentiles
        durations_cursor = conn.execute(
            "SELECT duration_ms FROM traces WHERE endpoint = ? AND ts_epoch >= ? ORDER BY duration_ms",
            (endpoint, cutoff),
        )
        durations = [r[0] for r in durations_cursor.fetchall()]

        # Error count
        err_cursor = conn.execute(
            "SELECT COUNT(*) FROM traces WHERE endpoint = ? AND ts_epoch >= ? AND status_code >= 400",
            (endpoint, cutoff),
        )
        error_count = err_cursor.fetchone()[0]

        return {
            "endpoint": endpoint,
            "count": row[0],
            "avg_ms": row[1],
            "min_ms": row[2],
            "max_ms": row[3],
            "p50": _percentile(durations, 50),
            "p95": _percentile(durations, 95),
            "p99": _percentile(durations, 99),
            "avg_request_size": row[4],
            "avg_response_size": row[5],
            "error_count": error_count,
            "error_rate": error_count / row[0] if row[0] > 0 else 0,
        }

    def get_total_requests(self, hours: int = 24) -> int:
        """Get total request count."""
        conn = self._get_conn()
        cutoff = time.time() - (hours * 3600)
        cursor = conn.execute("SELECT COUNT(*) FROM traces WHERE ts_epoch >= ?", (cutoff,))
        return cursor.fetchone()[0]

    def get_timeline(self, endpoint: str, hours: int = 24, buckets: int = 30) -> list[dict]:
        """Get a time-bucketed latency timeline for an endpoint."""
        conn = self._get_conn()
        cutoff = time.time() - (hours * 3600)
        bucket_size = (hours * 3600) / buckets

        cursor = conn.execute(
            """SELECT
                CAST((ts_epoch - ?) / ? AS INTEGER) as bucket,
                AVG(duration_ms) as avg_ms,
                MAX(duration_ms) as max_ms,
                COUNT(*) as count
               FROM traces
               WHERE endpoint = ? AND ts_epoch >= ?
               GROUP BY bucket
               ORDER BY bucket""",
            (cutoff, bucket_size, endpoint, cutoff),
        )

        return [
            {
                "bucket": row[0],
                "avg_ms": row[1],
                "max_ms": row[2],
                "count": row[3],
                "time_start": cutoff + row[0] * bucket_size,
            }
            for row in cursor.fetchall()
        ]


def _percentile(sorted_list: list[float], p: int) -> float:
    """Calculate a percentile from a sorted list."""
    if not sorted_list:
        return 0.0
    k = (len(sorted_list) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_list):
        return sorted_list[-1]
    return sorted_list[f] + (k - f) * (sorted_list[c] - sorted_list[f])
