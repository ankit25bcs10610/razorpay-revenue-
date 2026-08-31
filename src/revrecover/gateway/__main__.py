"""Run the full gateway locally:  make serve

- POST /webhooks/razorpay  — signed Razorpay test-mode events in
- POST /admin/process      — drive the worker (x-admin-token header)
- GET  /dashboard          — live auto-refreshing case dashboard

Configuration (all env, no baked-in credentials):
  RAZORPAY_WEBHOOK_SECRET  webhook HMAC secret; generated + printed if unset
  ADMIN_TOKEN              admin endpoint token; generated + printed if unset
  GATEWAY_HOST             bind address (default 127.0.0.1)
  AUDIT_DB                 SQLite audit path (default gateway-audit.db)
"""

import os
from pathlib import Path

import uvicorn

from revrecover.gateway.app import create_app
from revrecover.gateway.config import resolve_secret
from revrecover.gateway.pipeline import RecoveryService
from revrecover.policy.compliance import ComplianceEngine
from revrecover.storage.sqlite import SqliteAuditChain

POLICY = Path(__file__).parents[3] / "policy" / "compliance.yaml"

webhook_secret, webhook_generated = resolve_secret("RAZORPAY_WEBHOOK_SECRET")
admin_token, admin_generated = resolve_secret("ADMIN_TOKEN")

service = RecoveryService(
    engine=ComplianceEngine.from_yaml(POLICY),
    audit=SqliteAuditChain(os.environ.get("AUDIT_DB", "gateway-audit.db")),
)
app = create_app(
    webhook_secret=webhook_secret,
    intake=service.enqueue,
    processor=service.process_pending,
    admin_token=admin_token,
    dashboard=service.render_dashboard,
)

if __name__ == "__main__":
    if webhook_generated:
        print(f"RAZORPAY_WEBHOOK_SECRET not set — generated for this run: {webhook_secret}")
    if admin_generated:
        print(f"ADMIN_TOKEN not set — generated for this run: {admin_token}")
    uvicorn.run(app, host=os.environ.get("GATEWAY_HOST", "127.0.0.1"), port=8000)
