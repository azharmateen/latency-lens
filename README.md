# latency-lens

**Auto-instrument your API and get a performance dashboard with AI-powered optimization suggestions.** Add one line of middleware. See every endpoint's P50/P95/P99. Get told exactly what to fix.

```python
from latency_lens import LatencyLensMiddleware
app.add_middleware(LatencyLensMiddleware)
```

That's it. Open `localhost:9090` for the dashboard.

---

## Demo

```
$ latency-lens report --ai

  LATENCY LENS REPORT
  Period: last 24 hours
  Total requests: 14,832
  Unique endpoints: 23
  Error rate: 2.1%

  ENDPOINT PERFORMANCE
  -------------------------------------------------------------------
  Endpoint                             P50      P95      P99     Req
  -------------------------------------------------------------------
  /api/users/:id/orders               12ms    478ms   2340ms   3,210
  /api/search                         45ms    312ms   1890ms   2,104
  /api/products                        8ms     23ms     89ms   5,441
  ...

  DETECTED PATTERNS
  -------------------------------------------------------------------
  !!! [N+1] /api/users/:id/orders: 47 sequential requests in 200ms
  !!  [SLOW] /api/search has P99=1890ms. Add caching or pagination.
  !!  [ERRORS] /api/webhooks has 12.4% error rate.

  AI Suggestions:
  1. Add a batch endpoint for /api/users/:id/orders (~47x fewer calls)
  2. Cache /api/search with 60s TTL (estimated 80% hit rate)
  3. Add circuit breaker on /api/webhooks upstream dependency
```

---

## Quickstart

```bash
# Install
pip install latency-lens

# Or from source
git clone https://github.com/yourname/latency-lens.git
cd latency-lens
pip install -e .

# Setup middleware
latency-lens init --framework fastapi

# Start the dashboard
latency-lens serve

# Generate a report
latency-lens report

# With AI suggestions
export OPENAI_API_KEY=sk-...
latency-lens report --ai
```

---

## Framework Integration

### FastAPI

```python
from fastapi import FastAPI
from latency_lens import LatencyLensMiddleware

app = FastAPI()
app.add_middleware(LatencyLensMiddleware, db_path="./latency_lens.db")
```

### Flask

```python
from flask import Flask
from latency_lens import latency_lens_middleware

app = Flask(__name__)
latency_lens_middleware(app, db_path="./latency_lens.db")
```

### Any ASGI app

```python
from latency_lens import LatencyLensMiddleware
app = LatencyLensMiddleware(app, db_path="./latency_lens.db")
```

---

## Features

- **One-line setup** -- ASGI/WSGI middleware, zero config
- **Auto-records everything** -- endpoint, method, duration, status, request/response size
- **Local SQLite storage** -- no external services, no data leaves your machine
- **Web dashboard** -- Chart.js charts for latency distribution and request volume
- **Pattern detection** -- finds N+1 queries, slow endpoints, error hotspots, oversized responses
- **AI advisor** -- sends perf data to LLM, gets specific optimization suggestions
- **Multiple export formats** -- JSON, OpenTelemetry, Prometheus metrics
- **Path normalization** -- automatically groups `/users/123` and `/users/456` as `/users/:id`

---

## Architecture

```
Your API
   |
   v
[Middleware] ---- records every request
   |
   v
[SQLite Collector] ---- stores traces locally
   |
   v
[Analyzer] ---- P50/P95/P99, N+1 detection, error hotspots
   |
   +---> [Dashboard] ---- Flask app with Chart.js
   +---> [AI Advisor] ---- LLM-powered suggestions
   +---> [Exporters] ---- JSON, OpenTelemetry, Prometheus
```

---

## CLI Reference

```
latency-lens init [OPTIONS]
  --framework [auto|fastapi|flask|django|express]
  --db-path PATH          SQLite database path

latency-lens serve [OPTIONS]
  --db-path PATH          SQLite database path
  --host HOST             Dashboard host (default: 127.0.0.1)
  --port PORT             Dashboard port (default: 9090)

latency-lens report [OPTIONS]
  --db-path PATH          SQLite database path
  --format [terminal|json|otel|prometheus]
  --hours INT             Analysis window (default: 24)
  --ai/--no-ai            Include AI suggestions
```

---

## License

MIT License. See [LICENSE](./LICENSE).
