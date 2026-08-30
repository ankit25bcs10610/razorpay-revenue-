# RevRecover — AI Revenue Recovery Agent

**Razorpay AI Buildathon · Track 3: AI Revenue Recovery**

An autonomous, auditable agent that finds revenue slipping away — failed
payments, halted subscriptions, overdue invoices — decides the right
intervention, and wins the money back inside hard compliance bounds.

```
RevRecover — measured batch run (seed=2026, n=400)
====================================================
  Revenue at risk        ₹   1,910,471
  Recovered by agent     ₹   1,299,512  (68.0%)
  Baseline: do nothing   ₹     213,788
  Baseline: naive retry  ₹     832,293
  Incremental recovery   ₹   1,085,724
----------------------------------------------------
  Cases: 255 recovered / 4 escalated / 141 abandoned
  Contacts sent: 531 (false-positive/annoyance: 24)
  Audit chain: 2281 records, intact=True
```

That report is fully reproducible: `make demo` re-runs the same seeded
400-case batch end to end on your machine.

## The one-sentence design

**LLMs reason and communicate; deterministic code moves money.** The LLM
diagnoses causes and recommends playbooks — every answer schema-validated,
every failure mode degrading to a rule engine — while retries, nudges, and
stopping rules are enforced by code the model cannot override.

## Quickstart

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync          # install dependencies
make test        # 102 tests
make demo        # measured 400-case recovery batch (no API keys needed)
make serve       # webhook gateway on :8000 (Razorpay test-mode webhooks)
```

The demo batch is deterministic and LLM-free by default. To enable live
Claude diagnosis, set `ANTHROPIC_API_KEY` and pass
`Diagnostician(AnthropicDiagnosisClient())` into `run_case` — on any API
failure the agent silently degrades to its rule engine and keeps working.

## How it maps to the judging bar

| The bar asks for | Where it lives |
|---|---|
| **Measured money recovered across a batch** | `evaluation/batch.py` — seeded scenario generator + frozen persona simulator (including never-payers, so 100% recovery is impossible), do-nothing and naive-retry baselines, incremental ₹ reported |
| **Stopping rules** | `workflows/flow.py` — finite playbooks, attempt caps, opt-out honored immediately; a case always terminates with a reason. Test: `test_never_payer_stops_after_max_attempts_never_a_fourth` |
| **Compliant escalation** | `policy/compliance.yaml` + `policy/compliance.py` — quiet hours (RBI collection norms, IST), weekly contact caps, min-gap, never-retry codes, HITL approval above ₹50k, kill switch. Escalating to a human is always allowed |
| **Audit trail** | `audit/chain.py` — append-only, hash-chained ledger; editing or deleting any record breaks `verify()` at the exact broken record. Every stage (DETECT → DIAGNOSE → DECIDE → ACT → OUTCOME) is recorded with its reasoning |
| **Honest false-positive cost** | The batch report counts contacts sent to customers who would have paid anyway |

## Architecture

Full design in [ARCHITECTURE.md](ARCHITECTURE.md). The loop:

```
detect → diagnose → decide → act → measure → learn
```

| Layer | Module | What it does |
|---|---|---|
| Ingestion | `gateway/` | FastAPI webhook gateway: HMAC signature verification, event dedupe, Razorpay events → domain cases |
| Detection | `detection/scorer.py` | Recoverability scoring; hard failures (blocked card, fraud) are never pursued |
| Diagnosis | `diagnosis/` | Claude structured-output diagnosis over a PII-free evidence pack, deterministic rule fallback on any failure |
| Decision + Compliance | `policy/` | Policy-as-code filter — a non-compliant action can never be selected |
| Execution | `workflows/flow.py` | Bounded playbooks (dunning, smart retry, receivables, checkout) behind an action gate |
| Actuators | `actuators/razorpay_client.py` | Razorpay test-mode Payment Links with idempotent reference IDs |
| Memory | `domain/models.py` | Case lifecycle state machine; illegal transitions raise |
| Audit | `audit/chain.py` | Tamper-evident decision ledger |
| Evaluation | `evaluation/` | Scenario generator, persona simulator, batch runner with baselines |

## The LLM boundary

| The LLM does | The LLM never does |
|---|---|
| Diagnose root causes over structured evidence | Execute a retry or move money |
| Recommend a playbook (validated against a closed set) | Pass its own compliance check |
| Write the human-readable audit summary | Extend attempts past stopping rules |
| — | See customer identifiers (evidence packs are PII-free, tested) |

A hallucinated playbook name, malformed JSON, out-of-range confidence, or an
API outage all land in the same place: the deterministic rule engine, with
`source: "fallback"` recorded in the audit chain.

## Try the webhook gateway

```bash
make serve   # RAZORPAY_WEBHOOK_SECRET defaults to whsec_demo
```

```bash
BODY='{"event":"payment.failed","payload":{"payment":{"entity":{"id":"pay_DEMO1","amount":249900,"customer_id":"cust_1","error_reason":"insufficient_funds"}}}}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac whsec_demo | awk '{print $2}')
curl -s -X POST http://127.0.0.1:8000/webhooks/razorpay \
  -H "content-type: application/json" \
  -H "x-razorpay-signature: $SIG" \
  -H "x-razorpay-event-id: evt_demo_1" \
  -d "$BODY"
# → {"status":"accepted","case_id":"case_pay_DEMO1"}
```

Replay the same event: `{"status":"duplicate"}`. Tamper with the body:
`401`. That's the gateway contract in three curls.

## Development

Built test-first: every module's tests were written and watched fail before
the implementation existed. `uv run pytest` runs the full suite in under a
second — no network, no API keys, fully deterministic.

## Roadmap

- **Durable workflows** — lift `run_case`'s loop into Temporal (real
  24-hour waits, crash recovery); the flow's semantics are already
  clock-injected so they transfer unchanged
- **Dashboard** — render audit chains as per-case timeline cards
- **Learned policy** — Thompson-sampling bandit over playbook variants,
  gated by offline holdout evaluation (never allowed to relax compliance)
