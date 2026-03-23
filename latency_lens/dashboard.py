"""
Flask mini-app serving the performance dashboard.
"""

import json
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

from .collector import TraceCollector
from .analyzer import TraceAnalyzer


def create_dashboard_app(db_path: str) -> Flask:
    """Create and configure the dashboard Flask app."""
    app = Flask(__name__)
    collector = TraceCollector(db_path)
    analyzer = TraceAnalyzer(collector)

    # Load the HTML template
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    if template_path.exists():
        dashboard_html = template_path.read_text()
    else:
        dashboard_html = "<h1>Template not found</h1>"

    @app.route("/")
    def index():
        return render_template_string(dashboard_html)

    @app.route("/api/analysis")
    def api_analysis():
        hours = request.args.get("hours", 24, type=int)
        analysis = analyzer.analyze(hours=hours)
        return jsonify(analysis)

    @app.route("/api/endpoints")
    def api_endpoints():
        hours = request.args.get("hours", 24, type=int)
        endpoints = collector.get_endpoints(hours)
        stats = [collector.get_endpoint_stats(ep, hours) for ep in endpoints]
        stats = [s for s in stats if s.get("count", 0) > 0]
        stats.sort(key=lambda x: x.get("p95", 0), reverse=True)
        return jsonify(stats)

    @app.route("/api/endpoint/<path:endpoint>/timeline")
    def api_timeline(endpoint):
        hours = request.args.get("hours", 24, type=int)
        endpoint = "/" + endpoint
        timeline = collector.get_timeline(endpoint, hours)
        return jsonify(timeline)

    @app.route("/api/endpoint/<path:endpoint>/traces")
    def api_traces(endpoint):
        hours = request.args.get("hours", 24, type=int)
        endpoint = "/" + endpoint
        traces = collector.query_traces(hours=hours, endpoint=endpoint, limit=100)
        return jsonify(traces)

    @app.route("/api/patterns")
    def api_patterns():
        hours = request.args.get("hours", 24, type=int)
        analysis = analyzer.analyze(hours=hours)
        return jsonify(analysis.get("patterns", []))

    return app
