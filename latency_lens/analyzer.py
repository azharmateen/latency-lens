"""
Trace analyzer: finds slow endpoints, detects N+1 patterns, identifies error hotspots.
"""

from .collector import TraceCollector


class TraceAnalyzer:
    """Analyzes collected traces to identify performance issues."""

    # Thresholds
    SLOW_P95_MS = 500       # P95 > 500ms = slow
    SLOW_P99_MS = 2000      # P99 > 2s = very slow
    HIGH_ERROR_RATE = 0.05  # > 5% error rate = problem
    N_PLUS_1_THRESHOLD = 10 # Many fast sequential calls to same endpoint

    def __init__(self, collector: TraceCollector):
        self.collector = collector

    def analyze(self, hours: int = 24) -> dict:
        """Run full analysis on recent traces."""
        endpoints = self.collector.get_endpoints(hours)
        total_requests = self.collector.get_total_requests(hours)

        endpoint_stats = []
        for ep in endpoints:
            stats = self.collector.get_endpoint_stats(ep, hours)
            if stats.get("count", 0) > 0:
                endpoint_stats.append(stats)

        # Sort by P95 descending (slowest first)
        endpoint_stats.sort(key=lambda x: x.get("p95", 0), reverse=True)

        # Detect patterns
        patterns = []
        patterns.extend(self._detect_slow_endpoints(endpoint_stats))
        patterns.extend(self._detect_n_plus_1(hours))
        patterns.extend(self._detect_error_hotspots(endpoint_stats))
        patterns.extend(self._detect_size_anomalies(endpoint_stats))

        # Calculate overall error rate
        total_errors = sum(s.get("error_count", 0) for s in endpoint_stats)
        error_rate = total_errors / total_requests if total_requests > 0 else 0

        return {
            "summary": {
                "hours": hours,
                "total_requests": total_requests,
                "unique_endpoints": len(endpoints),
                "error_rate": error_rate,
                "total_errors": total_errors,
            },
            "endpoints": endpoint_stats,
            "patterns": patterns,
        }

    def _detect_slow_endpoints(self, stats: list[dict]) -> list[dict]:
        """Find endpoints with high latency."""
        patterns = []

        for s in stats:
            p95 = s.get("p95", 0)
            p99 = s.get("p99", 0)

            if p99 > self.SLOW_P99_MS:
                patterns.append({
                    "type": "slow",
                    "severity": "high",
                    "endpoint": s["endpoint"],
                    "description": (
                        f"{s['endpoint']} has P99={p99:.0f}ms (P95={p95:.0f}ms). "
                        f"Consider adding caching, optimizing queries, or reducing payload size."
                    ),
                    "metrics": {"p95": p95, "p99": p99, "count": s["count"]},
                })
            elif p95 > self.SLOW_P95_MS:
                patterns.append({
                    "type": "slow",
                    "severity": "medium",
                    "endpoint": s["endpoint"],
                    "description": (
                        f"{s['endpoint']} has P95={p95:.0f}ms. "
                        f"Consider adding response caching or pagination."
                    ),
                    "metrics": {"p95": p95, "p99": p99, "count": s["count"]},
                })

        return patterns

    def _detect_n_plus_1(self, hours: int) -> list[dict]:
        """
        Detect N+1 query patterns: many fast sequential requests to the same endpoint
        in a short time window, suggesting a loop calling the API.
        """
        patterns = []
        traces = self.collector.query_traces(hours=hours, limit=5000)

        if not traces:
            return patterns

        # Group by endpoint
        by_endpoint: dict[str, list[dict]] = {}
        for t in traces:
            by_endpoint.setdefault(t["endpoint"], []).append(t)

        for endpoint, ep_traces in by_endpoint.items():
            if len(ep_traces) < self.N_PLUS_1_THRESHOLD:
                continue

            # Sort by timestamp
            ep_traces.sort(key=lambda t: t["ts_epoch"])

            # Look for bursts: many requests within 2 seconds
            burst_count = 0
            burst_start = ep_traces[0]["ts_epoch"]

            for i in range(1, len(ep_traces)):
                gap = ep_traces[i]["ts_epoch"] - ep_traces[i - 1]["ts_epoch"]

                if gap < 0.1:  # Less than 100ms between requests
                    burst_count += 1
                else:
                    if burst_count >= self.N_PLUS_1_THRESHOLD:
                        avg_ms = sum(t["duration_ms"] for t in ep_traces[i - burst_count:i]) / burst_count
                        patterns.append({
                            "type": "n+1",
                            "severity": "high",
                            "endpoint": endpoint,
                            "description": (
                                f"N+1 pattern detected on {endpoint}: {burst_count} sequential requests "
                                f"with avg {avg_ms:.0f}ms each. "
                                f"Consider batch/bulk endpoint or data loader."
                            ),
                            "metrics": {"burst_count": burst_count, "avg_ms": avg_ms},
                        })
                    burst_count = 0

        return patterns

    def _detect_error_hotspots(self, stats: list[dict]) -> list[dict]:
        """Find endpoints with high error rates."""
        patterns = []

        for s in stats:
            error_rate = s.get("error_rate", 0)
            if error_rate > self.HIGH_ERROR_RATE and s["count"] >= 5:
                patterns.append({
                    "type": "errors",
                    "severity": "high" if error_rate > 0.2 else "medium",
                    "endpoint": s["endpoint"],
                    "description": (
                        f"{s['endpoint']} has {error_rate:.1%} error rate "
                        f"({s['error_count']}/{s['count']} requests). "
                        f"Check server logs for root cause."
                    ),
                    "metrics": {"error_rate": error_rate, "error_count": s["error_count"]},
                })

        return patterns

    def _detect_size_anomalies(self, stats: list[dict]) -> list[dict]:
        """Find endpoints with unusually large responses."""
        patterns = []

        for s in stats:
            avg_resp = s.get("avg_response_size", 0)
            if avg_resp > 1_000_000:  # > 1 MB average response
                patterns.append({
                    "type": "large_response",
                    "severity": "medium",
                    "endpoint": s["endpoint"],
                    "description": (
                        f"{s['endpoint']} returns avg {avg_resp / 1024:.0f}KB responses. "
                        f"Consider pagination, compression, or field selection."
                    ),
                    "metrics": {"avg_response_size": avg_resp},
                })

        return patterns
