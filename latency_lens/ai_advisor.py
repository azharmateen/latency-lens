"""
AI-powered performance advisor: sends trace analysis to LLM for optimization suggestions.
"""

import json
from typing import Any

from openai import OpenAI


class AIAdvisor:
    """Generates AI-powered optimization suggestions from performance data."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def suggest_sync(self, analysis: dict) -> str:
        """Generate optimization suggestions (synchronous)."""
        if not self.api_key:
            return self._fallback_suggestions(analysis)

        prompt = self._build_prompt(analysis)

        try:
            client = OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a backend performance optimization expert. "
                            "Analyze API performance data and give specific, actionable "
                            "optimization suggestions. Be concise. Reference specific "
                            "endpoints and metrics. Prioritize by impact."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"AI advisor error: {e}\n\n" + self._fallback_suggestions(analysis)

    def _build_prompt(self, analysis: dict) -> str:
        """Build the prompt from analysis data."""
        summary = analysis.get("summary", {})
        endpoints = analysis.get("endpoints", [])[:10]
        patterns = analysis.get("patterns", [])

        lines = [
            "Analyze this API performance data and provide optimization suggestions.",
            "",
            f"Total requests: {summary.get('total_requests', 0)}",
            f"Unique endpoints: {summary.get('unique_endpoints', 0)}",
            f"Error rate: {summary.get('error_rate', 0):.2%}",
            "",
            "Top endpoints by P95 latency:",
        ]

        for ep in endpoints:
            lines.append(
                f"  {ep['endpoint']} - "
                f"P50={ep.get('p50', 0):.0f}ms P95={ep.get('p95', 0):.0f}ms P99={ep.get('p99', 0):.0f}ms "
                f"({ep.get('count', 0)} reqs, {ep.get('error_rate', 0):.1%} errors, "
                f"avg resp {ep.get('avg_response_size', 0):.0f}B)"
            )

        if patterns:
            lines.append("")
            lines.append("Detected issues:")
            for p in patterns:
                lines.append(f"  [{p['type'].upper()}] {p['description']}")

        lines.extend([
            "",
            "Provide:",
            "1. Top 3 highest-impact optimizations with estimated improvement",
            "2. Quick wins that can be done immediately",
            "3. Architecture suggestions for long-term improvement",
        ])

        return "\n".join(lines)

    def _fallback_suggestions(self, analysis: dict) -> str:
        """Generate rule-based suggestions when AI is not available."""
        suggestions = []
        patterns = analysis.get("patterns", [])
        endpoints = analysis.get("endpoints", [])

        for pattern in patterns:
            if pattern["type"] == "n+1":
                suggestions.append(
                    f"N+1 PATTERN: {pattern['endpoint']}\n"
                    f"  - Create a batch/bulk endpoint\n"
                    f"  - Use a DataLoader pattern\n"
                    f"  - Estimated improvement: ~{pattern['metrics'].get('burst_count', 10)}x fewer requests"
                )
            elif pattern["type"] == "slow":
                ep = pattern["endpoint"]
                p95 = pattern["metrics"].get("p95", 0)
                suggestions.append(
                    f"SLOW ENDPOINT: {ep} (P95={p95:.0f}ms)\n"
                    f"  - Add response caching (Redis/in-memory)\n"
                    f"  - Check for missing database indexes\n"
                    f"  - Consider async processing for heavy operations"
                )
            elif pattern["type"] == "errors":
                suggestions.append(
                    f"ERROR HOTSPOT: {pattern['endpoint']} ({pattern['metrics'].get('error_rate', 0):.1%})\n"
                    f"  - Add structured error logging\n"
                    f"  - Implement retry with backoff for upstream calls\n"
                    f"  - Add circuit breaker pattern"
                )
            elif pattern["type"] == "large_response":
                suggestions.append(
                    f"LARGE RESPONSE: {pattern['endpoint']}\n"
                    f"  - Add pagination (limit/offset or cursor)\n"
                    f"  - Enable gzip compression\n"
                    f"  - Use field selection (GraphQL or sparse fieldsets)"
                )

        # General suggestions based on overall stats
        summary = analysis.get("summary", {})
        if summary.get("error_rate", 0) > 0.05:
            suggestions.append(
                "HIGH OVERALL ERROR RATE\n"
                "  - Implement health check endpoints\n"
                "  - Add structured error tracking (Sentry/Datadog)\n"
                "  - Review error handling middleware"
            )

        if not suggestions:
            suggestions.append("No significant issues detected. Performance looks healthy.")

        return "\n\n".join(suggestions)
