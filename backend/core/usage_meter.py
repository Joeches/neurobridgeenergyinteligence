"""
NeuroBridge 11D - Persistent Usage Meter
SQLite-backed usage tracking for SaaS monetization.
Prometheus Metrics Instrumented - API Usage Observability
"""

from __future__ import annotations

import sqlite3
import threading
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# PROMETHEUS METRICS IMPORT - SAFE WITH FALLBACK
# ============================================================================

try:
    from backend.monitoring.prometheus_metrics import (
        record_external_request,
        set_investor_clients_active,
        metrics,
    )
    _METRICS_AVAILABLE = metrics.available if metrics else False
except ImportError:
    _METRICS_AVAILABLE = False
    def record_external_request(*args, **kwargs): pass
    def set_investor_clients_active(*args, **kwargs): pass

if _METRICS_AVAILABLE:
    logger.info("[USAGE_METER] prometheus metrics instrumented")
else:
    logger.debug("[USAGE_METER] prometheus metrics unavailable - running without instrumentation")


class UsageMeter:
    """
    Persistent usage meter with SQLite backend for SaaS monetization.
    
    Tracks API usage per client with daily, monthly, and rate-based limits.
    Instrumented with Prometheus metrics for observability.
    """
    
    def __init__(self, db_path: str = "data/neurobridge_external_api.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()
        logger.info(f"[USAGE_METER] initialized db={self.db_path}")

    def _connect(self) -> sqlite3.Connection:
        """Create a new database connection with row factory."""
        try:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            return conn
        except sqlite3.Error as e:
            logger.error(f"[USAGE_METER] Connection failed: {e}")
            raise

    def _init_db(self) -> None:
        """Initialize database schema with indexes."""
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS api_usage_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        client_id TEXT NOT NULL,
                        endpoint TEXT NOT NULL,
                        timestamp INTEGER NOT NULL,
                        day_key TEXT NOT NULL,
                        month_key TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_usage_client_time
                    ON api_usage_events(client_id, timestamp)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_usage_day
                    ON api_usage_events(client_id, day_key)
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_usage_month
                    ON api_usage_events(client_id, month_key)
                    """
                )
                conn.commit()
                logger.debug("[USAGE_METER] database schema initialized")
        except sqlite3.Error as e:
            logger.error(f"[USAGE_METER] Database init failed: {e}")
            raise

    def _today_key(self) -> str:
        """Get today's date key (YYYY-MM-DD)."""
        return time.strftime("%Y-%m-%d")

    def _month_key(self) -> str:
        """Get current month key (YYYY-MM)."""
        return time.strftime("%Y-%m")

    def record(self, client_id: str, endpoint: str) -> Dict[str, Any]:
        """
        Record an API usage event.
        
        Args:
            client_id: Client identifier
            endpoint: API endpoint that was called
            
        Returns:
            Usage summary after recording
        """
        record_start = time.time()
        now = int(time.time())
        day_key = self._today_key()
        month_key = self._month_key()

        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO api_usage_events
                    (client_id, endpoint, timestamp, day_key, month_key)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (client_id, endpoint, now, day_key, month_key),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[USAGE_METER] Record failed for client={client_id}: {e}")
            # Return degraded summary even on failure
            return {
                "client_id": client_id,
                "endpoint": endpoint,
                "total": 0,
                "daily": 0,
                "monthly": 0,
                "rate_last_minute": 0,
                "error": str(e),
            }

        # Get summary after recording
        summary = self.get_usage_summary(client_id, endpoint)
        
        # PROMETHEUS: Record API request with latency
        try:
            record_latency = time.time() - record_start
            record_external_request(
                route=endpoint,
                method="POST",  # Usage recording is always a "write"
                status=200,
                latency_seconds=record_latency
            )
        except Exception:
            pass
        
        return summary

    def get_usage_summary(self, client_id: str, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """
        Get usage summary for a client.
        
        Args:
            client_id: Client identifier
            endpoint: Optional endpoint filter
            
        Returns:
            Usage summary dictionary
        """
        now = int(time.time())
        minute_ago = now - 60
        day_key = self._today_key()
        month_key = self._month_key()

        try:
            with self._lock, self._connect() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) AS c FROM api_usage_events WHERE client_id = ?",
                    (client_id,),
                ).fetchone()["c"]

                daily = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM api_usage_events
                    WHERE client_id = ? AND day_key = ?
                    """,
                    (client_id, day_key),
                ).fetchone()["c"]

                monthly = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM api_usage_events
                    WHERE client_id = ? AND month_key = ?
                    """,
                    (client_id, month_key),
                ).fetchone()["c"]

                rate_last_minute = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM api_usage_events
                    WHERE client_id = ? AND timestamp >= ?
                    """,
                    (client_id, minute_ago),
                ).fetchone()["c"]

            return {
                "client_id": client_id,
                "endpoint": endpoint,
                "total": int(total),
                "daily": int(daily),
                "monthly": int(monthly),
                "rate_last_minute": int(rate_last_minute),
            }
        except sqlite3.Error as e:
            logger.error(f"[USAGE_METER] Summary query failed for client={client_id}: {e}")
            return {
                "client_id": client_id,
                "endpoint": endpoint,
                "total": 0,
                "daily": 0,
                "monthly": 0,
                "rate_last_minute": 0,
                "error": str(e),
            }

    def check_limits(self, client_id: str, limits: Dict[str, int]) -> Dict[str, Any]:
        """
        Check if client has exceeded their usage limits.
        
        Args:
            client_id: Client identifier
            limits: Dict with daily_requests, monthly_requests, rate_per_minute
            
        Returns:
            Limit check result with allowed flag
        """
        try:
            usage = self.get_usage_summary(client_id)

            allowed = (
                usage["daily"] < limits.get("daily_requests", 1000)
                and usage["monthly"] < limits.get("monthly_requests", 30000)
                and usage["rate_last_minute"] < limits.get("rate_per_minute", 100)
            )

            result = {
                "allowed": allowed,
                "daily_used": usage["daily"],
                "monthly_used": usage["monthly"],
                "rate_last_minute": usage["rate_last_minute"],
                "limits": limits,
            }
            
            # PROMETHEUS: Track rate limit exceeded
            if not allowed:
                try:
                    record_external_request(
                        route="rate_limit_check",
                        method="GET",
                        status=429,
                        latency_seconds=0.0
                    )
                except Exception:
                    pass
            
            return result
        except Exception as e:
            logger.error(f"[USAGE_METER] Limit check failed for client={client_id}: {e}")
            return {
                "allowed": False,
                "daily_used": 0,
                "monthly_used": 0,
                "rate_last_minute": 0,
                "limits": limits,
                "error": str(e),
            }

    def get_endpoint_breakdown(self, client_id: str) -> list[Dict[str, Any]]:
        """
        Get endpoint usage breakdown for a client.
        
        Args:
            client_id: Client identifier
            
        Returns:
            List of endpoint usage counts
        """
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT endpoint, COUNT(*) AS count
                    FROM api_usage_events
                    WHERE client_id = ?
                    GROUP BY endpoint
                    ORDER BY count DESC
                    """,
                    (client_id,),
                ).fetchall()

            return [
                {
                    "endpoint": row["endpoint"],
                    "count": int(row["count"]),
                }
                for row in rows
            ]
        except sqlite3.Error as e:
            logger.error(f"[USAGE_METER] Breakdown query failed for client={client_id}: {e}")
            return []

    def get_client_usage(self, client_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get detailed client usage history for admin views.
        
        Args:
            client_id: Client identifier
            days: Number of days to look back
            
        Returns:
            Detailed usage dictionary
        """
        now = int(time.time())
        cutoff = now - (days * 86400)
        
        try:
            with self._lock, self._connect() as conn:
                total_requests = conn.execute(
                    "SELECT COUNT(*) AS c FROM api_usage_events WHERE client_id = ? AND timestamp >= ?",
                    (client_id, cutoff),
                ).fetchone()["c"]
                
                last_request = conn.execute(
                    "SELECT MAX(timestamp) AS ts FROM api_usage_events WHERE client_id = ?",
                    (client_id,),
                ).fetchone()["ts"]
                
                # Get daily breakdown
                daily_rows = conn.execute(
                    """
                    SELECT day_key, COUNT(*) AS count
                    FROM api_usage_events
                    WHERE client_id = ? AND timestamp >= ?
                    GROUP BY day_key
                    ORDER BY day_key DESC
                    LIMIT ?
                    """,
                    (client_id, cutoff, days),
                ).fetchall()
                
                daily_breakdown = {
                    row["day_key"]: int(row["count"])
                    for row in daily_rows
                }
            
            return {
                "client_id": client_id,
                "total_requests": int(total_requests),
                "last_request_at": last_request,
                "daily_breakdown": daily_breakdown,
                "lookback_days": days,
            }
        except sqlite3.Error as e:
            logger.error(f"[USAGE_METER] Client usage query failed for client={client_id}: {e}")
            return {
                "client_id": client_id,
                "total_requests": 0,
                "last_request_at": None,
                "daily_breakdown": {},
                "lookback_days": days,
                "error": str(e),
            }

    def get_active_client_count(self) -> int:
        """
        Get count of distinct active clients in the last 24 hours.
        Used for Prometheus investor_clients_active metric.
        """
        now = int(time.time())
        cutoff = now - 86400  # 24 hours
        
        try:
            with self._lock, self._connect() as conn:
                count = conn.execute(
                    """
                    SELECT COUNT(DISTINCT client_id) AS c
                    FROM api_usage_events
                    WHERE timestamp >= ?
                    """,
                    (cutoff,),
                ).fetchone()["c"]
                
                active_count = int(count)
                
                # PROMETHEUS: Update active investor clients count
                try:
                    set_investor_clients_active(active_count)
                except Exception:
                    pass
                
                return active_count
        except sqlite3.Error as e:
            logger.error(f"[USAGE_METER] Active client count failed: {e}")
            return 0

    def get_global_stats(self) -> Dict[str, Any]:
        """
        Get global usage statistics across all clients.
        """
        try:
            with self._lock, self._connect() as conn:
                total_events = conn.execute(
                    "SELECT COUNT(*) AS c FROM api_usage_events"
                ).fetchone()["c"]
                
                total_clients = conn.execute(
                    "SELECT COUNT(DISTINCT client_id) AS c FROM api_usage_events"
                ).fetchone()["c"]
                
                active_clients = self.get_active_client_count()
            
            return {
                "total_events": int(total_events),
                "total_clients": int(total_clients),
                "active_clients_24h": active_clients,
                "db_path": str(self.db_path),
                "metrics_instrumented": _METRICS_AVAILABLE,
            }
        except sqlite3.Error as e:
            logger.error(f"[USAGE_METER] Global stats failed: {e}")
            return {
                "total_events": 0,
                "total_clients": 0,
                "active_clients_24h": 0,
                "db_path": str(self.db_path),
                "error": str(e),
            }

    def health_check(self) -> Dict[str, Any]:
        """
        Health check for the usage meter.
        """
        try:
            with self._lock, self._connect() as conn:
                conn.execute("SELECT 1 FROM api_usage_events LIMIT 1")
            
            return {
                "status": "healthy",
                "db_path": str(self.db_path),
                "db_exists": self.db_path.exists(),
                "metrics_instrumented": _METRICS_AVAILABLE,
            }
        except sqlite3.Error as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "db_path": str(self.db_path),
                "db_exists": self.db_path.exists(),
            }
        except Exception as e:
            return {
                "status": "degraded",
                "error": str(e),
                "db_path": str(self.db_path),
            }


_usage_meter: Optional[UsageMeter] = None
_meter_lock = threading.RLock()


def get_usage_meter() -> UsageMeter:
    """
    Get or create the singleton UsageMeter instance.
    Thread-safe initialization.
    """
    global _usage_meter

    if _usage_meter is None:
        with _meter_lock:
            if _usage_meter is None:
                try:
                    _usage_meter = UsageMeter()
                    logger.info("[USAGE_METER] singleton created")
                except Exception as e:
                    logger.error(f"[USAGE_METER] Singleton creation failed: {e}")
                    raise

    return _usage_meter


def reset_usage_meter():
    """
    Reset the usage meter singleton.
    Useful for testing.
    """
    global _usage_meter
    with _meter_lock:
        _usage_meter = None
        logger.info("[USAGE_METER] singleton reset")