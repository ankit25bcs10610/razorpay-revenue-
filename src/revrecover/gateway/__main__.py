"""Run the full gateway locally:  make serve

- POST /webhooks/razorpay  — signed Razorpay test-mode events in
- POST /admin/process      — drive the worker (x-admin-token header)
- GET  /dashboard          — live auto-refreshing case dashboard

Env: RAZORPAY_WEBHOOK_SECRET (default whsec_demo),
     ADMIN_TOKEN (default admin_demo), GATEWAY_HOST (default 127.0.0.1).
"""

import os
from pathlib import Path

import uvicorn

from revrecover.gateway.app import create_app
from revrecover.gateway.pipeline import RecoveryService
from revrecover.policy.compliance import ComplianceEngine
from revrecover.storage.sqlite import SqliteAuditChain

POLICY = Path(__file__).parents[3] / "policy" / "compliance.yaml"

service = RecoveryService(
    engine=ComplianceEngine.from_yaml(POLICY),
    audit=SqliteAuditChain(os.environ.get("AUDIT_DB", "gateway-audit.db")),
)
app = create_app(
    webhook_secret=os.environ.get("RAZORPAY_WEBHOOK_SECRET", "whsec_demo"),
    intake=service.enqueue,
    processor=service.process_pending,
    admin_token=os.environ.get("ADMIN_TOKEN", "admin_demo"),
    dashboard=service.render_dashboard,
)

if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("GATEWAY_HOST", "127.0.0.1"), port=8000)
