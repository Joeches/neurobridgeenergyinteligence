from __future__ import annotations

import statistics
import threading
import time
from collections import defaultdict, deque
from typing import Dict, Any


class LatencyMetrics:
    def __init__(self, max_samples: int = 5000) -> None:
        self.max_samples = max_samples
        self.samples = defaultdict(lambda: deque(maxlen=max_samples))
        self._lock = threading.RLock()

    def record(self, endpoint: str, latency_ms: float) -> None:
        with self._lock:
            self.samples[endpoint].append(float(latency_ms))

    def percentile(self, values, p: float) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        idx = int(round((p / 100) * (len(values) - 1)))
        return round(values[idx], 3)

    def summary(self, endpoint: str | None = None) -> Dict[str, Any]:
        with self._lock:
            keys = [endpoint] if endpoint else list(self.samples.keys())
            result = {}

            for key in keys:
                values = list(self.samples.get(key, []))
                if not values:
                    result[key] = {"count": 0}
                    continue

                jitter = 0.0
                if len(values) > 1:
                    jitter = statistics.mean(
                        abs(values[i] - values[i - 1])
                        for i in range(1, len(values))
                    )

                result[key] = {
                    "count": len(values),
                    "min_ms": round(min(values), 3),
                    "avg_ms": round(statistics.mean(values), 3),
                    "max_ms": round(max(values), 3),
                    "p95_ms": self.percentile(values, 95),
                    "p99_ms": self.percentile(values, 99),
                    "jitter_ms": round(jitter, 3),
                }

            return result


_latency_metrics = LatencyMetrics()


def get_latency_metrics() -> LatencyMetrics:
    return _latency_metrics