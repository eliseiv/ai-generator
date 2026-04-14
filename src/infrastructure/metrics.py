from prometheus_client import Counter, Histogram

api_requests_total = Counter(
    "api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status_code"],
)

generation_requests_total = Counter(
    "generation_requests_total",
    "Total generation requests",
    ["type", "status"],
)

generation_errors_total = Counter(
    "generation_errors_total",
    "Total generation errors",
    ["type", "error_type"],
)

generation_cost_total = Counter(
    "generation_cost_total",
    "Total generation cost in tokens",
    ["type"],
)

generation_duration_seconds = Histogram(
    "generation_duration_seconds",
    "Generation duration from submit to completion",
    ["type"],
    buckets=[5, 10, 30, 60, 120, 180, 300],
)
