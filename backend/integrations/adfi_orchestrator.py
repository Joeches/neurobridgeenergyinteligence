"""
NeuroBridge 11D - ADFI Orchestrator

Production-safe ADFI orchestration layer.

Purpose:
- Restore get_orchestrator()
- Avoid import failures
- Provide deterministic source registration
- Validate Phase 1 compliance
- Route telemetry into ADFI-style normalized payloads
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("NeuroBridge.ADFIOrchestrator")


class DataSourceType(str, Enum):
    HARDWARE_MODBUS = "hardware_modbus"
    SUNGROW_ISOLARCLOUD = "sungrow_isolarcloud"
    NASA_POWER = "nasa_power"
    GOOGLE_EARTH_ENGINE = "google_earth_engine"
    OPENWEATHER = "openweather"
    SYNTHETIC = "synthetic"
    MANUAL = "manual"


class SourceStatus(str, Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    DISABLED = "disabled"


@dataclass
class RegisteredSource:
    source_id: str
    source_type: DataSourceType
    name: str
    priority: int = 10
    status: SourceStatus = SourceStatus.ACTIVE
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: int = field(default_factory=lambda: int(time.time()))


@dataclass
class ADFIDataPoint:
    source_id: str
    source_type: DataSourceType
    payload: Dict[str, Any]
    quality_score: float
    validation_status: str
    timestamp: int = field(default_factory=lambda: int(time.time()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ADFIOrchestrator:
    VERSION = "4.1.0-PHASE1-PRODUCTION"

    MAX_EVENTS = 1000

    BLOCKED_SOURCE_KEYWORDS = {
        "nuclear",
        "fusion",
        "quantum",
        "defense",
        "missile",
        "weapon",
    }

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sources: Dict[str, RegisteredSource] = {}
        self._events: Deque[Dict[str, Any]] = deque(maxlen=self.MAX_EVENTS)
        self._started_at = int(time.time())

        logger.info("[ADFI] Orchestrator initialized | version=%s", self.VERSION)

    def _now(self) -> int:
        return int(time.time())

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            result = float(value)
            if result != result or result in (float("inf"), float("-inf")):
                return None
            return result
        except (TypeError, ValueError):
            return None

    def _append_event(self, event: Dict[str, Any]) -> None:
        safe_event = {
            **event,
            "timestamp": event.get("timestamp", self._now()),
        }

        with self._lock:
            self._events.append(safe_event)

    def _to_source_type(self, value: Any) -> DataSourceType:
        if isinstance(value, DataSourceType):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()
            for item in DataSourceType:
                if item.value == normalized:
                    return item

        return DataSourceType.MANUAL

    def _to_source_status(self, value: Any) -> SourceStatus:
        if isinstance(value, SourceStatus):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()
            for item in SourceStatus:
                if item.value == normalized:
                    return item

        return SourceStatus.DEGRADED

    def _is_blocked(self, text: str) -> Optional[str]:
        lowered = text.lower()

        for keyword in sorted(self.BLOCKED_SOURCE_KEYWORDS):
            if keyword in lowered:
                return keyword

        return None

    def register_source(
        self,
        source_type: Any,
        name: str,
        priority: int = 10,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegisteredSource:
        safe_name = str(name).strip() if name else "unnamed_source"
        safe_metadata = metadata if isinstance(metadata, dict) else {}

        blocked = self._is_blocked(f"{source_type} {safe_name} {safe_metadata}")

        if blocked:
            logger.warning(
                "[ADFI] Blocked source registration attempt | blocked=%s | name=%s",
                blocked,
                safe_name,
            )
            raise ValueError(
                f"ADFI source rejected: '{blocked}' is excluded from Phase 1 production"
            )

        source_enum = self._to_source_type(source_type)
        source_id = f"{source_enum.value}:{uuid.uuid4().hex[:12]}"

        try:
            safe_priority = max(1, int(priority))
        except (TypeError, ValueError):
            safe_priority = 10

        source = RegisteredSource(
            source_id=source_id,
            source_type=source_enum,
            name=safe_name,
            priority=safe_priority,
            metadata=safe_metadata,
        )

        with self._lock:
            self._sources[source_id] = source
            self._events.append(
                {
                    "event": "source_registered",
                    "source_id": source_id,
                    "source_type": source_enum.value,
                    "name": safe_name,
                    "timestamp": self._now(),
                }
            )

        logger.info(
            "[ADFI] Source registered | id=%s | type=%s | priority=%s",
            source_id,
            source_enum.value,
            safe_priority,
        )

        return source

    def list_sources(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "source_id": source.source_id,
                    "source_type": source.source_type.value,
                    "name": source.name,
                    "priority": source.priority,
                    "status": source.status.value,
                    "metadata": source.metadata,
                    "registered_at": source.registered_at,
                }
                for source in self._sources.values()
            ]

    def list_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        try:
            safe_limit = max(1, min(int(limit), self.MAX_EVENTS))
        except (TypeError, ValueError):
            safe_limit = 100

        with self._lock:
            return list(self._events)[-safe_limit:]

    def set_source_status(self, source_id: str, status: SourceStatus) -> bool:
        safe_status = self._to_source_status(status)

        with self._lock:
            if source_id not in self._sources:
                logger.warning("[ADFI] Source status update failed | unknown_id=%s", source_id)
                return False

            self._sources[source_id].status = safe_status
            self._events.append(
                {
                    "event": "source_status_changed",
                    "source_id": source_id,
                    "status": safe_status.value,
                    "timestamp": self._now(),
                }
            )

        logger.info(
            "[ADFI] Source status changed | id=%s | status=%s",
            source_id,
            safe_status.value,
        )

        return True

    def validate_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deterministic physics/telemetry validation.

        This is intentionally conservative and production-safe.
        """

        issues: List[str] = []
        warnings: List[str] = []

        if not isinstance(payload, dict):
            return {
                "valid": False,
                "issues": ["payload_not_dictionary"],
                "warnings": [],
                "quality_score": 0.0,
                "validation_status": "invalid",
            }

        voltage = payload.get("voltage_v")
        frequency = payload.get("frequency_hz")
        power_kw = payload.get("power_kw")
        current_a = payload.get("current_a")
        actual_kw = payload.get("actual_kw")
        expected_kw = payload.get("expected_kw")
        timestamp = payload.get("timestamp")

        voltage_f = self._safe_float(voltage)
        frequency_f = self._safe_float(frequency)
        power_f = self._safe_float(power_kw)
        current_f = self._safe_float(current_a)
        actual_f = self._safe_float(actual_kw)
        expected_f = self._safe_float(expected_kw)

        if voltage is not None:
            if voltage_f is None:
                issues.append("voltage_invalid")
            elif not 0 <= voltage_f <= 1000:
                issues.append("voltage_out_of_range")
            elif voltage_f < 180 or voltage_f > 260:
                warnings.append("voltage_outside_nominal_band")

        if frequency is not None:
            if frequency_f is None:
                issues.append("frequency_invalid")
            elif not 45 <= frequency_f <= 65:
                issues.append("frequency_out_of_range")
            elif abs(frequency_f - 50.0) >= 1.0:
                warnings.append("frequency_drift_detected")

        if power_kw is not None:
            if power_f is None:
                issues.append("power_invalid")
            elif power_f < 0:
                issues.append("negative_power")

        if current_a is not None:
            if current_f is None:
                issues.append("current_invalid")
            elif current_f < 0:
                issues.append("negative_current")

        if actual_kw is not None:
            if actual_f is None:
                issues.append("actual_kw_invalid")
            elif actual_f < 0:
                issues.append("negative_actual_kw")

        if expected_kw is not None:
            if expected_f is None:
                issues.append("expected_kw_invalid")
            elif expected_f < 0:
                issues.append("negative_expected_kw")

        if actual_f is not None and expected_f is not None and expected_f > 0:
            deviation_ratio = abs(actual_f - expected_f) / expected_f
            if deviation_ratio >= 0.35:
                warnings.append("solar_actual_expected_deviation_high")

        if voltage_f is not None and current_f is not None and power_f is not None:
            estimated_kw = (voltage_f * current_f) / 1000.0
            if estimated_kw > 0:
                consistency_gap = abs(power_f - estimated_kw) / estimated_kw
                if consistency_gap >= 0.35:
                    warnings.append("power_voltage_current_consistency_gap")

        if timestamp is not None:
            timestamp_f = self._safe_float(timestamp)
            if timestamp_f is None:
                warnings.append("timestamp_invalid")
            else:
                age_seconds = self._now() - int(timestamp_f)
                if age_seconds > 900:
                    warnings.append("telemetry_stale")
                elif age_seconds < -120:
                    warnings.append("timestamp_from_future")

        quality_score = 1.0
        quality_score -= len(issues) * 0.25
        quality_score -= len(warnings) * 0.08
        quality_score = max(0.0, min(1.0, quality_score))

        if issues:
            validation_status = "invalid"
        elif warnings:
            validation_status = "warning"
        else:
            validation_status = "valid"

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "quality_score": round(quality_score, 3),
            "validation_status": validation_status,
        }

    def ingest(
        self,
        source_id: str,
        payload: Dict[str, Any],
    ) -> ADFIDataPoint:
        with self._lock:
            source = self._sources.get(source_id)

        if not source:
            logger.error("[ADFI] Ingest rejected | unknown source_id=%s", source_id)
            raise KeyError(f"Unknown ADFI source_id: {source_id}")

        if source.status == SourceStatus.DISABLED:
            logger.warning("[ADFI] Ingest rejected | disabled source_id=%s", source_id)
            raise RuntimeError(f"ADFI source disabled: {source_id}")

        validation = self.validate_payload(payload)

        datapoint = ADFIDataPoint(
            source_id=source_id,
            source_type=source.source_type,
            payload={
                **payload,
                "_adfi": {
                    "source_name": source.name,
                    "priority": source.priority,
                    "phase": "PHASE_1_PRODUCTION",
                    "orchestrator_version": self.VERSION,
                    "source_status": source.status.value,
                },
            },
            quality_score=validation["quality_score"],
            validation_status=validation["validation_status"],
        )

        self._append_event(
            {
                "event": "payload_ingested",
                "source_id": source_id,
                "trace_id": datapoint.trace_id,
                "quality_score": datapoint.quality_score,
                "validation_status": datapoint.validation_status,
                "issues": validation.get("issues", []),
                "warnings": validation.get("warnings", []),
                "timestamp": datapoint.timestamp,
            }
        )

        return datapoint

    def health(self) -> Dict[str, Any]:
        with self._lock:
            active = sum(1 for src in self._sources.values() if src.status == SourceStatus.ACTIVE)
            degraded = sum(1 for src in self._sources.values() if src.status == SourceStatus.DEGRADED)
            disabled = sum(1 for src in self._sources.values() if src.status == SourceStatus.DISABLED)
            total = len(self._sources)
            event_count = len(self._events)

        return {
            "status": "ok",
            "version": self.VERSION,
            "phase": "PHASE_1_PRODUCTION",
            "uptime_seconds": self._now() - self._started_at,
            "sources": {
                "total": total,
                "active": active,
                "degraded": degraded,
                "disabled": disabled,
            },
            "events": {
                "stored": event_count,
                "max": self.MAX_EVENTS,
            },
            "blocked_domains": sorted(self.BLOCKED_SOURCE_KEYWORDS),
            "timestamp": self._now(),
        }

    def compliance_report(self) -> Dict[str, Any]:
        with self._lock:
            source_count = len(self._sources)
            active_sources = sum(
                1 for source in self._sources.values() if source.status == SourceStatus.ACTIVE
            )

        return {
            "phase": "PHASE_1_PRODUCTION",
            "allowed_scope": [
                "solar_optimization",
                "grid_stability",
                "aece",
                "telemetry",
                "hardware_bridge",
            ],
            "blocked_domains": sorted(self.BLOCKED_SOURCE_KEYWORDS),
            "source_count": source_count,
            "active_source_count": active_sources,
            "status": "compliant",
            "timestamp": self._now(),
        }


_orchestrator: Optional[ADFIOrchestrator] = None
_lock = threading.RLock()


def get_orchestrator() -> ADFIOrchestrator:
    global _orchestrator

    if _orchestrator is None:
        with _lock:
            if _orchestrator is None:
                _orchestrator = ADFIOrchestrator()

    return _orchestrator


def reset_orchestrator() -> None:
    global _orchestrator

    with _lock:
        _orchestrator = None