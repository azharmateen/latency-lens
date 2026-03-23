"""
Export trace analysis to various formats:
- JSON (generic)
- OpenTelemetry format
- Prometheus metrics format
"""

import time
from datetime import datetime, timezone


def export_json(analysis: dict) -> dict:
    """Export analysis as a structured JSON report."""
    return {
        "tool": "latency-lens",
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": analysis.get("summary", {}),
        "endpoints": [
            {
                "endpoint": ep.get("endpoint", ""),
                "count": ep.get("count", 0),
                "latency": {
                    "avg_ms": round(ep.get("avg_ms", 0), 2),
                    "min_ms": round(ep.get("min_ms", 0), 2),
                    "max_ms": round(ep.get("max_ms", 0), 2),
                    "p50_ms": round(ep.get("p50", 0), 2),
                    "p95_ms": round(ep.get("p95", 0), 2),
                    "p99_ms": round(ep.get("p99", 0), 2),
                },
                "error_rate": round(ep.get("error_rate", 0), 4),
                "avg_request_size": round(ep.get("avg_request_size", 0), 0),
                "avg_response_size": round(ep.get("avg_response_size", 0), 0),
            }
            for ep in analysis.get("endpoints", [])
        ],
        "patterns": analysis.get("patterns", []),
    }


def export_otel(analysis: dict) -> dict:
    """
    Export analysis in OpenTelemetry-compatible format.
    This generates resource metrics following the OTLP JSON schema.
    """
    now_ns = int(time.time() * 1_000_000_000)

    metrics = []

    for ep in analysis.get("endpoints", []):
        endpoint = ep.get("endpoint", "/unknown")

        # Request duration histogram summary
        metrics.append({
            "name": "http.server.request.duration",
            "description": "Duration of HTTP server requests",
            "unit": "ms",
            "sum": {
                "dataPoints": [
                    {
                        "attributes": [
                            {"key": "http.route", "value": {"stringValue": endpoint}},
                        ],
                        "startTimeUnixNano": str(now_ns - 86400 * 1_000_000_000),
                        "timeUnixNano": str(now_ns),
                        "asDouble": round(ep.get("avg_ms", 0) * ep.get("count", 0), 2),
                        "quantileValues": [
                            {"quantile": 0.5, "value": round(ep.get("p50", 0), 2)},
                            {"quantile": 0.95, "value": round(ep.get("p95", 0), 2)},
                            {"quantile": 0.99, "value": round(ep.get("p99", 0), 2)},
                        ],
                    }
                ],
                "isMonotonic": True,
                "aggregationTemporality": 2,
            },
        })

        # Request count
        metrics.append({
            "name": "http.server.request.count",
            "description": "Number of HTTP server requests",
            "unit": "1",
            "sum": {
                "dataPoints": [
                    {
                        "attributes": [
                            {"key": "http.route", "value": {"stringValue": endpoint}},
                        ],
                        "startTimeUnixNano": str(now_ns - 86400 * 1_000_000_000),
                        "timeUnixNano": str(now_ns),
                        "asInt": str(ep.get("count", 0)),
                    }
                ],
                "isMonotonic": True,
                "aggregationTemporality": 2,
            },
        })

        # Error count
        if ep.get("error_count", 0) > 0:
            metrics.append({
                "name": "http.server.request.error.count",
                "description": "Number of failed HTTP server requests",
                "unit": "1",
                "sum": {
                    "dataPoints": [
                        {
                            "attributes": [
                                {"key": "http.route", "value": {"stringValue": endpoint}},
                            ],
                            "timeUnixNano": str(now_ns),
                            "asInt": str(ep.get("error_count", 0)),
                        }
                    ],
                    "isMonotonic": True,
                    "aggregationTemporality": 2,
                },
            })

    return {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "latency-lens"}},
                        {"key": "service.version", "value": {"stringValue": "1.0.0"}},
                    ],
                },
                "scopeMetrics": [
                    {
                        "scope": {"name": "latency-lens", "version": "1.0.0"},
                        "metrics": metrics,
                    }
                ],
            }
        ],
    }


def export_prometheus(analysis: dict) -> str:
    """Export analysis as Prometheus exposition format text."""
    lines = [
        "# HELP http_request_duration_ms HTTP request duration in milliseconds",
        "# TYPE http_request_duration_ms summary",
    ]

    for ep in analysis.get("endpoints", []):
        endpoint = ep.get("endpoint", "/unknown")
        labels = f'endpoint="{endpoint}"'

        count = ep.get("count", 0)
        total = round(ep.get("avg_ms", 0) * count, 2)

        lines.append(f'http_request_duration_ms{{quantile="0.5",{labels}}} {ep.get("p50", 0):.2f}')
        lines.append(f'http_request_duration_ms{{quantile="0.95",{labels}}} {ep.get("p95", 0):.2f}')
        lines.append(f'http_request_duration_ms{{quantile="0.99",{labels}}} {ep.get("p99", 0):.2f}')
        lines.append(f'http_request_duration_ms_sum{{{labels}}} {total}')
        lines.append(f'http_request_duration_ms_count{{{labels}}} {count}')

    lines.extend([
        "",
        "# HELP http_request_errors_total Total HTTP request errors",
        "# TYPE http_request_errors_total counter",
    ])

    for ep in analysis.get("endpoints", []):
        endpoint = ep.get("endpoint", "/unknown")
        errors = ep.get("error_count", 0)
        if errors > 0:
            lines.append(f'http_request_errors_total{{endpoint="{endpoint}"}} {errors}')

    lines.extend([
        "",
        "# HELP http_response_size_bytes Average HTTP response size",
        "# TYPE http_response_size_bytes gauge",
    ])

    for ep in analysis.get("endpoints", []):
        endpoint = ep.get("endpoint", "/unknown")
        resp_size = ep.get("avg_response_size", 0)
        lines.append(f'http_response_size_bytes{{endpoint="{endpoint}"}} {resp_size:.0f}')

    return "\n".join(lines) + "\n"
