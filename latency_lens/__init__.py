"""latency-lens - Auto-instrument APIs and show performance maps with AI suggestions."""

__version__ = "1.0.0"

from .middleware import LatencyLensMiddleware, latency_lens_middleware

__all__ = ["LatencyLensMiddleware", "latency_lens_middleware"]
