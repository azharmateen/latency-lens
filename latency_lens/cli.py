"""CLI interface for latency-lens."""

import os
from pathlib import Path

import click


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """latency-lens: Auto-instrument APIs and visualize performance."""
    pass


@cli.command()
@click.option("--framework", default="auto", type=click.Choice(["auto", "fastapi", "flask", "django", "express"]),
              help="Target framework")
@click.option("--db-path", default="./latency_lens.db", help="SQLite database path for traces")
def init(framework, db_path):
    """Generate middleware setup instructions for your framework."""
    if framework == "auto":
        framework = _detect_framework()

    click.echo(f"\nlatency-lens setup for {framework}\n")

    if framework == "fastapi":
        click.echo("Add to your FastAPI app:\n")
        click.echo("  from latency_lens import LatencyLensMiddleware\n")
        click.echo("  app = FastAPI()")
        click.echo(f'  app.add_middleware(LatencyLensMiddleware, db_path="{db_path}")')

    elif framework == "flask":
        click.echo("Add to your Flask app:\n")
        click.echo("  from latency_lens import latency_lens_middleware\n")
        click.echo("  app = Flask(__name__)")
        click.echo(f'  latency_lens_middleware(app, db_path="{db_path}")')

    elif framework == "django":
        click.echo("Add to MIDDLEWARE in settings.py:\n")
        click.echo("  MIDDLEWARE = [")
        click.echo("      'latency_lens.DjangoLatencyLensMiddleware',")
        click.echo("      # ... other middleware")
        click.echo("  ]")
        click.echo(f'\n  LATENCY_LENS_DB = "{db_path}"')

    else:
        click.echo("Add the ASGI middleware to your app:\n")
        click.echo("  from latency_lens import LatencyLensMiddleware")
        click.echo(f'  app = LatencyLensMiddleware(app, db_path="{db_path}")')

    # Initialize the database
    from .collector import TraceCollector
    collector = TraceCollector(db_path)
    collector.init_db()
    click.echo(f"\nDatabase initialized at {db_path}")
    click.echo("Run `latency-lens serve` to view the dashboard.\n")


@cli.command()
@click.option("--db-path", default="./latency_lens.db", help="SQLite database path")
@click.option("--host", default="127.0.0.1", help="Dashboard host")
@click.option("--port", default=9090, help="Dashboard port")
def serve(db_path, host, port):
    """Start the performance dashboard."""
    if not Path(db_path).exists():
        click.echo(f"Database not found at {db_path}. Run `latency-lens init` first.")
        return

    from .dashboard import create_dashboard_app

    app = create_dashboard_app(db_path)
    click.echo(f"\nlatency-lens dashboard: http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False)


@cli.command()
@click.option("--db-path", default="./latency_lens.db", help="SQLite database path")
@click.option("--format", "output_format", default="terminal",
              type=click.Choice(["terminal", "json", "otel", "prometheus"]),
              help="Output format")
@click.option("--hours", default=24, help="Analysis window in hours")
@click.option("--ai/--no-ai", default=False, help="Include AI optimization suggestions")
def report(db_path, output_format, hours, ai):
    """Generate a performance report."""
    if not Path(db_path).exists():
        click.echo(f"Database not found at {db_path}. Run `latency-lens init` first.")
        return

    from .analyzer import TraceAnalyzer
    from .collector import TraceCollector
    from .exporters import export_json, export_otel, export_prometheus

    collector = TraceCollector(db_path)
    analyzer = TraceAnalyzer(collector)

    analysis = analyzer.analyze(hours=hours)

    if output_format == "terminal":
        _print_terminal_report(analysis)
    elif output_format == "json":
        import json
        print(json.dumps(export_json(analysis), indent=2))
    elif output_format == "otel":
        import json
        print(json.dumps(export_otel(analysis), indent=2))
    elif output_format == "prometheus":
        print(export_prometheus(analysis))

    if ai:
        click.echo("\nGenerating AI optimization suggestions...")
        from .ai_advisor import AIAdvisor
        advisor = AIAdvisor(api_key=os.getenv("OPENAI_API_KEY", ""))
        suggestions = advisor.suggest_sync(analysis)
        click.echo(suggestions)


def _detect_framework() -> str:
    """Auto-detect the web framework from project files."""
    if Path("requirements.txt").exists():
        content = Path("requirements.txt").read_text().lower()
        if "fastapi" in content:
            return "fastapi"
        if "flask" in content:
            return "flask"
        if "django" in content:
            return "django"

    if Path("pyproject.toml").exists():
        content = Path("pyproject.toml").read_text().lower()
        if "fastapi" in content:
            return "fastapi"
        if "flask" in content:
            return "flask"
        if "django" in content:
            return "django"

    if Path("package.json").exists():
        return "express"

    return "fastapi"


def _print_terminal_report(analysis: dict):
    """Print a terminal-friendly performance report."""
    endpoints = analysis.get("endpoints", [])
    patterns = analysis.get("patterns", [])
    summary = analysis.get("summary", {})

    click.echo("\n  LATENCY LENS REPORT")
    click.echo(f"  Period: last {summary.get('hours', 24)} hours")
    click.echo(f"  Total requests: {summary.get('total_requests', 0)}")
    click.echo(f"  Unique endpoints: {summary.get('unique_endpoints', 0)}")
    click.echo(f"  Error rate: {summary.get('error_rate', 0):.1%}")
    click.echo("")

    if endpoints:
        click.echo("  ENDPOINT PERFORMANCE")
        click.echo("  " + "-" * 70)
        click.echo(f"  {'Endpoint':<35} {'P50':>8} {'P95':>8} {'P99':>8} {'Req':>6}")
        click.echo("  " + "-" * 70)

        for ep in endpoints[:20]:
            click.echo(
                f"  {ep['endpoint']:<35} "
                f"{ep['p50']:>7.0f}ms "
                f"{ep['p95']:>7.0f}ms "
                f"{ep['p99']:>7.0f}ms "
                f"{ep['count']:>6}"
            )

    if patterns:
        click.echo(f"\n  DETECTED PATTERNS")
        click.echo("  " + "-" * 70)
        for pattern in patterns:
            icon = {"n+1": "!!!", "slow": "!!", "errors": "!!"}.get(pattern["type"], "!")
            click.echo(f"  {icon} [{pattern['type'].upper()}] {pattern['description']}")

    click.echo("")


if __name__ == "__main__":
    cli()
