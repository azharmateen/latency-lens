"""
ASGI/WSGI middleware for auto-recording request metrics.
Records: endpoint, method, duration, status code, request/response size, timestamp.
"""

import time
from typing import Callable

from .collector import TraceCollector


class LatencyLensMiddleware:
    """
    ASGI middleware that auto-records request latency and metadata.

    Usage with FastAPI:
        app.add_middleware(LatencyLensMiddleware, db_path="./latency_lens.db")

    Usage with any ASGI app:
        app = LatencyLensMiddleware(app, db_path="./latency_lens.db")
    """

    def __init__(self, app, db_path: str = "./latency_lens.db", **kwargs):
        # Handle both Starlette-style (app passed later) and direct wrapping
        if callable(app) and not isinstance(app, str):
            self.app = app
        else:
            self.app = None
            db_path = app if isinstance(app, str) else db_path

        self.collector = TraceCollector(db_path)
        self.collector.init_db()

    async def __call__(self, scope, receive, send):
        """ASGI entry point."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        method = scope.get("method", "GET")
        path = scope.get("path", "/")

        # Calculate request size from headers
        request_size = 0
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"content-length":
                try:
                    request_size = int(header_value)
                except ValueError:
                    pass

        # Capture response metadata
        status_code = 200
        response_size = 0

        async def send_wrapper(message):
            nonlocal status_code, response_size

            if message["type"] == "http.response.start":
                status_code = message.get("status", 200)
                for header_name, header_value in message.get("headers", []):
                    if header_name == b"content-length":
                        try:
                            response_size = int(header_value)
                        except ValueError:
                            pass

            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body and response_size == 0:
                    response_size = len(body)

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            status_code = 500
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Normalize path: replace UUID/ID segments with :id
            normalized_path = _normalize_path(path)

            self.collector.record(
                endpoint=normalized_path,
                method=method,
                status_code=status_code,
                duration_ms=duration_ms,
                request_size=request_size,
                response_size=response_size,
            )


def latency_lens_middleware(flask_app, db_path: str = "./latency_lens.db"):
    """
    Flask/WSGI middleware adapter.

    Usage:
        app = Flask(__name__)
        latency_lens_middleware(app, db_path="./latency_lens.db")
    """
    collector = TraceCollector(db_path)
    collector.init_db()

    @flask_app.before_request
    def before_request():
        from flask import request, g
        g._latency_lens_start = time.perf_counter()

    @flask_app.after_request
    def after_request(response):
        from flask import request, g

        start = getattr(g, "_latency_lens_start", None)
        if start is None:
            return response

        duration_ms = (time.perf_counter() - start) * 1000

        request_size = request.content_length or 0
        response_size = response.content_length or 0

        normalized_path = _normalize_path(request.path)

        collector.record(
            endpoint=normalized_path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_size=request_size,
            response_size=response_size,
        )

        return response

    return flask_app


def _normalize_path(path: str) -> str:
    """Normalize a URL path by replacing ID-like segments with :id."""
    import re
    parts = path.strip("/").split("/")
    normalized = []

    for part in parts:
        # UUID pattern
        if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', part, re.I):
            normalized.append(":id")
        # Numeric ID
        elif re.match(r'^\d+$', part):
            normalized.append(":id")
        # MongoDB ObjectId
        elif re.match(r'^[0-9a-f]{24}$', part, re.I):
            normalized.append(":id")
        else:
            normalized.append(part)

    return "/" + "/".join(normalized) if normalized else "/"
