"""
NeuroBridge 11D - Persistent External API Key Manager
SQLite-backed partner/investor API access layer.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional


class ApiPlan(str, Enum):
    INVESTOR_DEMO = "investor_demo"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


PLAN_LIMITS = {
    ApiPlan.INVESTOR_DEMO: {
        "daily_requests": 500,
        "monthly_requests": 5000,
        "rate_per_minute": 30,
    },
    ApiPlan.STARTER: {
        "daily_requests": 5000,
        "monthly_requests": 100000,
        "rate_per_minute": 120,
    },
    ApiPlan.PRO: {
        "daily_requests": 50000,
        "monthly_requests": 1000000,
        "rate_per_minute": 600,
    },
    ApiPlan.ENTERPRISE: {
        "daily_requests": 1000000,
        "monthly_requests": 50000000,
        "rate_per_minute": 5000,
    },
}


@dataclass
class ApiClient:
    client_id: str
    name: str
    api_key_hash: str
    plan: ApiPlan
    active: bool = True
    created_at: int = field(default_factory=lambda: int(time.time()))
    metadata: Dict[str, Any] = field(default_factory=dict)


class ApiKeyManager:
    def __init__(self, db_path: str = "data/neurobridge_external_api.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()
        self._bootstrap_cto_key()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_clients (
                    client_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL UNIQUE,
                    plan TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_clients_hash
                ON api_clients(api_key_hash)
                """
            )
            conn.commit()

    def _hash_key(self, raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def generate_key(self, prefix: str = "nb11d") -> str:
        return f"{prefix}_{secrets.token_urlsafe(32)}"

    def _metadata_to_json(self, metadata: Dict[str, Any]) -> str:
        import json
        return json.dumps(metadata or {}, default=str)

    def _metadata_from_json(self, value: str) -> Dict[str, Any]:
        import json
        try:
            return json.loads(value or "{}")
        except Exception:
            return {}

    def _row_to_client(self, row: sqlite3.Row) -> ApiClient:
        return ApiClient(
            client_id=row["client_id"],
            name=row["name"],
            api_key_hash=row["api_key_hash"],
            plan=ApiPlan(row["plan"]),
            active=bool(row["active"]),
            created_at=int(row["created_at"]),
            metadata=self._metadata_from_json(row["metadata_json"]),
        )

    def _bootstrap_cto_key(self) -> None:
        bootstrap_key = (
            os.getenv("NEUROBRIDGE_API_KEY")
            or os.getenv("CTO_API_KEY")
            or os.getenv("CTO_ACCESS_CODE")
            or os.getenv("API_KEY")
        )

        if not bootstrap_key:
            return

        self.register_existing_key(
            client_id="cto-root",
            name="CTO Root Access",
            raw_key=bootstrap_key,
            plan=ApiPlan.ENTERPRISE,
            metadata={"source": "environment"},
        )

    def register_existing_key(
        self,
        client_id: str,
        name: str,
        raw_key: str,
        plan: ApiPlan = ApiPlan.INVESTOR_DEMO,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ApiClient:
        api_key_hash = self._hash_key(raw_key)

        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO api_clients
                (client_id, name, api_key_hash, plan, active, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    client_id,
                    name,
                    api_key_hash,
                    plan.value,
                    1,
                    int(time.time()),
                    self._metadata_to_json(metadata or {}),
                ),
            )
            conn.commit()

        client = self.get_client(client_id)
        if client is None:
            raise RuntimeError("Failed to register API client")
        return client

    def create_client(
        self,
        name: str,
        plan: ApiPlan = ApiPlan.INVESTOR_DEMO,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raw_key = self.generate_key()
        client_id = f"client_{secrets.token_hex(8)}"

        client = self.register_existing_key(
            client_id=client_id,
            name=name,
            raw_key=raw_key,
            plan=plan,
            metadata=metadata or {},
        )

        return {
            "client_id": client.client_id,
            "name": client.name,
            "api_key": raw_key,
            "plan": client.plan.value,
            "limits": PLAN_LIMITS[client.plan],
            "created_at": client.created_at,
        }

    def get_client(self, client_id: str) -> Optional[ApiClient]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM api_clients WHERE client_id = ?",
                (client_id,),
            ).fetchone()

        return self._row_to_client(row) if row else None

    def verify_key(self, raw_key: Optional[str]) -> Optional[ApiClient]:
        if not raw_key:
            return None

        raw_hash = self._hash_key(raw_key)

        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM api_clients
                WHERE api_key_hash = ? AND active = 1
                """,
                (raw_hash,),
            ).fetchone()

        if not row:
            return None

        client = self._row_to_client(row)

        if hmac.compare_digest(raw_hash, client.api_key_hash):
            return client

        return None

    def deactivate_client(self, client_id: str) -> bool:
        with self._lock, self._connect() as conn:
            result = conn.execute(
                "UPDATE api_clients SET active = 0 WHERE client_id = ?",
                (client_id,),
            )
            conn.commit()
            return result.rowcount > 0

    def list_clients(self) -> list[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT client_id, name, plan, active, created_at, metadata_json
                FROM api_clients
                ORDER BY created_at DESC
                """
            ).fetchall()

        return [
            {
                "client_id": row["client_id"],
                "name": row["name"],
                "plan": row["plan"],
                "active": bool(row["active"]),
                "created_at": row["created_at"],
                "metadata": self._metadata_from_json(row["metadata_json"]),
            }
            for row in rows
        ]

    def get_limits(self, client: ApiClient) -> Dict[str, int]:
        return PLAN_LIMITS[client.plan]


_api_key_manager: Optional[ApiKeyManager] = None


def get_api_key_manager() -> ApiKeyManager:
    global _api_key_manager

    if _api_key_manager is None:
        _api_key_manager = ApiKeyManager()

    return _api_key_manager