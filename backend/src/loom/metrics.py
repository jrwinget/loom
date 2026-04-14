"""prometheus metrics for the loom backend.

all metric objects are module-level singletons so any module
can import and use them without passing state around.
"""

from prometheus_client import Counter, Gauge, Histogram

# -- upload tracking --
active_uploads = Gauge(
    "loom_active_uploads",
    "number of in-progress file uploads",
)

# -- ingest pipeline --
ingest_workflow_duration = Histogram(
    "loom_ingest_workflow_duration_seconds",
    "duration of ingest workflow activities",
    ["activity"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

# -- audit --
audit_failures = Counter(
    "loom_audit_failures_total",
    "number of failed audit log writes",
)

# -- auth --
auth_failures = Counter(
    "loom_auth_failures_total",
    "authentication failures by type",
    ["reason"],
)

# -- db pool --
db_pool_size = Gauge(
    "loom_db_pool_size",
    "total connections in the sqlalchemy pool",
)

db_pool_checked_out = Gauge(
    "loom_db_pool_checked_out",
    "connections currently checked out of the pool",
)
