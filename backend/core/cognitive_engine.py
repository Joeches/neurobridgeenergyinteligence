
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class CognitiveIntent(str, Enum):
    SOLAR_ANALYSIS = "solar_analysis"
    GRID_STABILITY = "grid_stability"
    RISK_ASSESSMENT = "risk_assessment"
    HARDWARE_STATUS = "hardware_status"
    TELEMETRY_STATUS = "telemetry_status"
    INVESTOR_DEMO = "investor_demo"
    SYSTEM_HEALTH = "system_health"
    COMPLIANCE_STATUS = "compliance_status"
    GENERAL = "general"


class CognitiveSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CognitiveContext:
    telemetry: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    system: Dict[str, Any] = field(default_factory=dict)
    user_role: str = "operator"
    phase: str = "PHASE_1_PRODUCTION"


@dataclass
class CognitiveDecision:
    intent: CognitiveIntent
    confidence: float
    severity: CognitiveSeverity
    summary: str
    explanation: str
    recommended_actions: List[str]
    evidence: Dict[str, Any]
    mode: str = "DETERMINISTIC_COGNITIVE_REASONING"
    generated_at: int = field(default_factory=lambda: int(time.time()))


class CognitiveEngine:
    """
    Lightweight deterministic cognitive engine.

    This does not pretend to be generative AI.
    It is explainable, testable, deterministic, and safe for production.
    """

    VERSION = "1.1.0-PHASE1-PRODUCTION"

    BLOCKED_DOMAINS: Set[str] = {
        "nuclear",
        "fusion",
        "quantum",
        "defense",
        "missile",
        "weapon",
    }

    PHASE1_ALLOWED_DOMAINS: Set[str] = {
        "solar",
        "grid",
        "battery",
        "telemetry",
        "hardware",
        "energy",
    }

    INTENT_KEYWORDS: Dict[CognitiveIntent, Set[str]] = {
        CognitiveIntent.SOLAR_ANALYSIS: {
            "solar",
            "pv",
            "irradiance",
            "panel",
            "inverter",
            "sun",
            "ses",
            "efficiency",
            "renewable",
            "generation",
        },
        CognitiveIntent.GRID_STABILITY: {
            "grid",
            "stability",
            "frequency",
            "voltage",
            "gsi",
            "load",
            "balance",
            "outage",
            "power quality",
        },
        CognitiveIntent.RISK_ASSESSMENT: {
            "risk",
            "danger",
            "failure",
            "fault",
            "anomaly",
            "unsafe",
            "critical",
            "threat",
            "alert",
        },
        CognitiveIntent.HARDWARE_STATUS: {
            "hardware",
            "modbus",
            "inverter",
            "meter",
            "relay",
            "device",
            "esp32",
            "sensor",
            "battery",
        },
        CognitiveIntent.TELEMETRY_STATUS: {
            "telemetry",
            "data",
            "pipeline",
            "adfi",
            "stream",
            "sensor",
            "ingestion",
            "payload",
        },
        CognitiveIntent.INVESTOR_DEMO: {
            "demo",
            "investor",
            "showcase",
            "presentation",
            "report",
            "pilot",
            "validation",
        },
        CognitiveIntent.SYSTEM_HEALTH: {
            "health",
            "status",
            "uptime",
            "redis",
            "celery",
            "cache",
            "prometheus",
            "service",
            "readiness",
        },
        CognitiveIntent.COMPLIANCE_STATUS: {
            "compliance",
            "phase",
            "blocked",
            "scope",
            "security",
            "audit",
            "isolation",
            "governance",
        },
    }

    def __init__(self) -> None:
        self.started_at = int(time.time())

    def _tokenize(self, text: str) -> Set[str]:
        """
        Tokenizes text safely to prevent substring false positives.

        Example:
        - "sun" matches "sun"
        - "sun" does not accidentally match unrelated embedded text
        """
        if not isinstance(text, str):
            return set()

        return set(re.findall(r"\b[a-zA-Z0-9_+-]+\b", text.lower()))

    def _contains_phrase_or_token(self, query: str, tokens: Set[str], keyword: str) -> bool:
        keyword_normalized = keyword.lower().strip()

        if not keyword_normalized:
            return False

        if " " in keyword_normalized:
            return keyword_normalized in query.lower()

        return keyword_normalized in tokens

    def detect_blocked_domain(self, query: str) -> Optional[str]:
        q = query.lower() if isinstance(query, str) else ""
        tokens = self._tokenize(q)

        for domain in sorted(self.BLOCKED_DOMAINS):
            if self._contains_phrase_or_token(q, tokens, domain):
                return domain

        return None

    def classify_intent(self, query: str) -> CognitiveIntent:
        q = query.lower() if isinstance(query, str) else ""
        tokens = self._tokenize(q)

        scores: Dict[CognitiveIntent, int] = {}

        for intent, keywords in self.INTENT_KEYWORDS.items():
            scores[intent] = sum(
                1 for word in keywords if self._contains_phrase_or_token(q, tokens, word)
            )

        best_intent = max(scores, key=scores.get)

        if scores[best_intent] <= 0:
            return CognitiveIntent.GENERAL

        return best_intent

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            result = float(value)

            if math.isnan(result) or math.isinf(result):
                return default

            return result

        except (TypeError, ValueError):
            return default

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(value, maximum))

    def compute_grid_stability_index(self, metrics: Dict[str, Any]) -> float:
        frequency = self._safe_float(metrics.get("frequency_hz"), 50.0)
        voltage = self._safe_float(metrics.get("voltage_v"), 230.0)
        load_balance = self._safe_float(metrics.get("load_balance"), 0.95)

        load_balance = self._clamp(load_balance, 0.0, 1.0)

        frequency_penalty = min(abs(frequency - 50.0) * 20.0, 40.0)
        voltage_penalty = min(abs(voltage - 230.0) / 230.0 * 100.0, 30.0)
        balance_penalty = min((1.0 - load_balance) * 30.0, 30.0)

        gsi = 100.0 - frequency_penalty - voltage_penalty - balance_penalty
        return round(self._clamp(gsi, 0.0, 100.0), 2)

    def compute_solar_efficiency_score(self, metrics: Dict[str, Any]) -> float:
        actual_kw = self._safe_float(metrics.get("actual_kw"), 0.0)
        expected_kw = self._safe_float(metrics.get("expected_kw"), max(actual_kw, 1.0))
        temperature_c = self._safe_float(metrics.get("temperature_c"), 30.0)
        irradiance_quality = self._safe_float(metrics.get("irradiance_quality"), 0.90)

        actual_kw = max(actual_kw, 0.0)
        expected_kw = max(expected_kw, 0.001)
        irradiance_quality = self._clamp(irradiance_quality, 0.0, 1.0)

        base = actual_kw / expected_kw
        temp_derate = max(0.70, 1.0 - max(temperature_c - 25.0, 0.0) * 0.004)

        score = base * temp_derate * irradiance_quality * 100.0
        return round(self._clamp(score, 0.0, 100.0), 2)

    def compute_risk_score(self, gsi: float, ses: float) -> float:
        gsi = self._clamp(gsi, 0.0, 100.0)
        ses = self._clamp(ses, 0.0, 100.0)

        risk = ((1.0 - gsi / 100.0) * 0.7) + ((1.0 - ses / 100.0) * 0.3)
        return round(self._clamp(risk, 0.0, 1.0), 4)

    def severity_from_risk(self, risk: float) -> CognitiveSeverity:
        risk = self._clamp(risk, 0.0, 1.0)

        if risk >= 0.80:
            return CognitiveSeverity.CRITICAL
        if risk >= 0.60:
            return CognitiveSeverity.HIGH
        if risk >= 0.35:
            return CognitiveSeverity.MEDIUM
        return CognitiveSeverity.LOW

    def confidence_from_intent(self, intent: CognitiveIntent, query: str) -> float:
        if intent == CognitiveIntent.GENERAL:
            return 0.72

        q = query.lower() if isinstance(query, str) else ""
        tokens = self._tokenize(q)
        keywords = self.INTENT_KEYWORDS.get(intent, set())

        hits = sum(1 for word in keywords if self._contains_phrase_or_token(q, tokens, word))
        confidence = 0.75 + hits * 0.04

        return round(self._clamp(confidence, 0.75, 0.99), 2)

    def _safe_context_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    def reason(self, query: str, context: Optional[CognitiveContext] = None) -> CognitiveDecision:
        context = context or CognitiveContext()

        safe_query = query.strip() if isinstance(query, str) else ""

        telemetry = self._safe_context_dict(context.telemetry)
        metrics = self._safe_context_dict(context.metrics)

        blocked_domain = self.detect_blocked_domain(safe_query)

        if blocked_domain:
            return CognitiveDecision(
                intent=CognitiveIntent.COMPLIANCE_STATUS,
                confidence=0.99,
                severity=CognitiveSeverity.HIGH,
                summary=f"{blocked_domain.title()} domain is excluded from Phase 1 production.",
                explanation=(
                    "The query touches a restricted domain. Phase 1 production only allows "
                    "solar optimization, grid stability, AECE, telemetry, and compliant hardware control."
                ),
                recommended_actions=[
                    "Use Phase 1 compliant solar, grid, battery, telemetry, or hardware endpoints.",
                    "Keep restricted modules blocked at route, import, task, and metrics level.",
                    "Record this blocked-domain event in the compliance audit trail.",
                ],
                evidence={
                    "blocked_domain": blocked_domain,
                    "phase": context.phase,
                    "allowed_domains": sorted(self.PHASE1_ALLOWED_DOMAINS),
                    "engine_version": self.VERSION,
                },
            )

        intent = self.classify_intent(safe_query)
        confidence = self.confidence_from_intent(intent, safe_query)

        merged_metrics = {
            **telemetry,
            **metrics,
        }

        gsi = self.compute_grid_stability_index(merged_metrics)
        ses = self.compute_solar_efficiency_score(merged_metrics)
        risk = self.compute_risk_score(gsi, ses)
        severity = self.severity_from_risk(risk)

        if intent == CognitiveIntent.SOLAR_ANALYSIS:
            summary = f"Solar efficiency score is {ses}/100."
            explanation = (
                "Solar reasoning used expected power, actual power, temperature derating, "
                "and irradiance quality to produce an explainable efficiency score."
            )
            actions = [
                "Compare actual inverter output against expected irradiance-adjusted output.",
                "Check panel temperature, dust, shading, inverter clipping, and battery charge state.",
                "Trigger AECE solar optimization when SES drops below the configured threshold.",
            ]

        elif intent == CognitiveIntent.GRID_STABILITY:
            summary = f"Grid stability index is {gsi}/100."
            explanation = (
                "Grid reasoning used frequency deviation, voltage deviation, and load balance "
                "to produce a deterministic stability index."
            )
            actions = [
                "Monitor frequency and voltage drift.",
                "Use AECE to reduce non-critical loads if instability increases.",
                "Escalate when GSI falls below production safety threshold.",
            ]

        elif intent == CognitiveIntent.RISK_ASSESSMENT:
            summary = f"Current deterministic risk score is {risk}."
            explanation = (
                "Risk is computed from grid stability and solar efficiency. "
                "The score is transparent, repeatable, and suitable for audit."
            )
            actions = [
                "Review GSI and SES contributors.",
                "Trigger emergency stop only if risk exceeds critical threshold.",
                "Record risk decision in compliance audit trail.",
            ]

        elif intent == CognitiveIntent.HARDWARE_STATUS:
            summary = "Hardware layer is Phase 1 scoped for solar inverter, grid meter, and battery storage."
            explanation = (
                "The cognitive layer treats hardware execution as guarded by Modbus, circuit breakers, "
                "Redis telemetry caching, and AECE safety controls."
            )
            actions = [
                "Verify Modbus connection health.",
                "Confirm simulation/live mode before demonstrations.",
                "Run safe read-only telemetry test before write actions.",
            ]

        elif intent == CognitiveIntent.TELEMETRY_STATUS:
            summary = "Telemetry should flow through ADFI into deterministic validation and AECE."
            explanation = (
                "The ADFI pipeline normalizes data, validates physical consistency, "
                "and sends trusted telemetry into the control system."
            )
            actions = [
                "Confirm ADFI orchestrator health.",
                "Validate source registration.",
                "Check pipeline latency and audit trail completeness.",
            ]

        elif intent == CognitiveIntent.INVESTOR_DEMO:
            summary = "Investor demo mode should expose remote, controlled, read-safe showcase flows."
            explanation = (
                "Demo sessions should prove before-and-after optimization, telemetry flow, "
                "system health, and compliance boundaries."
            )
            actions = [
                "Start a demo session through the demo endpoint.",
                "Generate a report after telemetry simulation completes.",
                "Show blocked-domain compliance as a governance strength.",
            ]

        elif intent == CognitiveIntent.SYSTEM_HEALTH:
            summary = "System health depends on FastAPI, Redis, Celery, Prometheus, cache, and circuit breakers."
            explanation = (
                "Production health should be evaluated using service availability, queue readiness, "
                "metrics registration, and control-loop readiness."
            )
            actions = [
                "Check Redis connectivity.",
                "Check Celery queues and beat schedule.",
                "Check Prometheus metrics endpoint.",
                "Check AECE and ADFI readiness.",
            ]

        elif intent == CognitiveIntent.COMPLIANCE_STATUS:
            summary = "Phase 1 compliance is based on strict domain isolation."
            explanation = (
                "Restricted domains must remain blocked across imports, routes, WebSockets, tasks, and metrics."
            )
            actions = [
                "Run compliance scan before deployment.",
                "Verify blocked endpoints return HTTP 403.",
                "Keep logs redacted in production.",
            ]

        else:
            summary = "System is operating in deterministic cognitive reasoning mode."
            explanation = (
                "The query did not match a specific energy intent. The system remains ready for "
                "solar, grid, telemetry, risk, hardware, demo, and compliance reasoning."
            )
            actions = [
                "Ask about solar efficiency, grid stability, AECE risk, telemetry, or demo readiness.",
            ]

        return CognitiveDecision(
            intent=intent,
            confidence=confidence,
            severity=severity,
            summary=summary,
            explanation=explanation,
            recommended_actions=actions,
            evidence={
                "gsi": gsi,
                "ses": ses,
                "risk": risk,
                "phase": context.phase,
                "engine_version": self.VERSION,
                "input_metrics": merged_metrics,
            },
        )


_engine: Optional[CognitiveEngine] = None


def get_cognitive_engine() -> CognitiveEngine:
    global _engine

    if _engine is None:
        _engine = CognitiveEngine()

    return _engine