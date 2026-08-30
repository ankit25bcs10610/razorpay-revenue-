"""Run the webhook gateway locally:  make serve

Point a Razorpay test-mode webhook (or curl) at POST /webhooks/razorpay.
Secret comes from RAZORPAY_WEBHOOK_SECRET (default: whsec_demo).
"""

import os

import uvicorn

from revrecover.audit.chain import AuditChain
from revrecover.gateway.app import create_app
from revrecover.gateway.service import DemoIntake

audit = AuditChain()
intake = DemoIntake(audit=audit)
app = create_app(
    webhook_secret=os.environ.get("RAZORPAY_WEBHOOK_SECRET", "whsec_demo"),
    intake=intake,
)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
