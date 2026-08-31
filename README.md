# RevRecover — AI Revenue Recovery Agent

**Razorpay AI Buildathon · Track 3: AI Revenue Recovery**

An autonomous, auditable agent that finds revenue slipping away — failed
payments, halted subscriptions, overdue invoices — decides the right
intervention, and wins the money back inside hard compliance bounds.

```
RevRecover — measured batch run (seed=2026, n=400)
========================================================
  Pursue floor 0.2 — tuned on a 100-case holdout (net ₹204,550), never on this batch
  Revenue at risk          ₹   1,859,405
  Recovered (static)       ₹     782,040  (42.1%)
  Recovered (learning)     ₹     907,129  (48.8%)
  Baseline: do nothing     ₹     137,659
  Baseline: naive retry    ₹     684,502
  Incremental (learning)   ₹     769,470
--------------------------------------------------------
  Learning curve (quartile recovery): 42.8% → 52.2% → 54.2% → 49.0%
  Cases: 198 recovered / 8 escalated / 194 abandoned
  Contacts sent: 534 (false-positive/annoyance: 29)
  Audit chain: 2547 records, intact=True
--------------------------------------------------------
  Recovered by playbook: checkout_recovery ₹113,715, dunning ₹353,013,
    receivables ₹178,567, smart_retry ₹219,686, update_method ₹42,148
  Stop reasons: attempts exhausted ×120, customer opted out ×17,
    high value unresolved ×8, not recoverable ×57, payment captured ×198
  Actions per recovery: 1.59 · time-to-recovery P50 1.0d / P95 2.0d
```

(The recovery rate *dropped* from earlier iterations as the simulator and
compliance got stricter — channel preferences, RBI e-mandate pre-debit
notices, EV gates. We kept the honest number.)

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
uv sync            # install dependencies
make test          # 206 tests, deterministic, ~1s, no network
make demo          # measured 400-case batch: holdout-tuned, static vs learning
make failure-demo  # issuer outage mid-retry, handled on camera
make dashboard     # self-contained dashboard.html: KPIs, learning curve,
                   #   every case's audit chain as a timeline card
make serve         # webhook gateway on :8000 (Razorpay test-mode webhooks)
```

Or containerized: `docker compose -f infra/docker-compose.yml up gateway`.

The demo batch is deterministic and LLM-free by default. To enable live
Claude diagnosis, set `ANTHROPIC_API_KEY` and pass
`Diagnostician(AnthropicDiagnosisClient())` into `run_case` — on any API
failure the agent silently degrades to its rule engine and keeps working.

## How it maps to the judging bar

| The bar asks for | Where it lives |
|---|---|
| **Measured money recovered across a batch** | `evaluation/batch.py` — seeded scenario generator + frozen persona simulator (including never-payers, so 100% recovery is impossible), do-nothing and naive-retry baselines, incremental ₹ reported |
| **Stopping rules** | `workflows/flow.py` — finite playbooks, attempt caps, opt-out honored immediately; a case always terminates with a reason. Test: `test_never_payer_stops_after_max_attempts_never_a_fourth` |
| **Compliant escalation** | `policy/compliance.yaml` + `policy/compliance.py` — quiet hours (RBI collection norms, IST), weekly contact caps (cross-case via Customer-360), min-gap, never-retry codes, **RBI e-mandate rules** (pre-debit notice, representment cap), daily action budget, HITL approval above ₹50k, dry-run mode, kill switch. Escalating to a human is always allowed |
| **Audit trail** | `audit/chain.py` (+ `storage/sqlite.py`, restart-proof) — append-only, hash-chained ledger; editing or deleting any record breaks `verify()` at the exact record. Every stage (DETECT → DIAGNOSE → **PLAN with considered-and-rejected alternatives and their EVs** → DECIDE → ACT → OUTCOME) is recorded with its reasoning |
| **Graceful failure handling** | `make failure-demo` — an issuer outage mid-retry is audited as ACT_FAILED, backed off, re-planned, and the case still recovers; the Razorpay client retries with backoff behind a circuit breaker |
| **Honest false-positive cost** | The batch report counts contacts sent to customers who would have paid anyway |
| **Improves across the batch** | `learning/bandit.py` — Thompson-sampling contextual bandit learns the best contact channel per customer segment; +₹1.2L over the static default on the same seed, quartile learning curve in the report. It re-ranks allowed choices only — every action still passes the compliance gate (tested: `test_chooser_cannot_bypass_the_kill_switch`) |

## Architecture

Full design in [ARCHITECTURE.md](ARCHITECTURE.md). The loop:

```
detect → diagnose → decide → act → measure → learn
```

| Layer | Module | What it does |
|---|---|---|
| Ingestion | `gateway/` | FastAPI webhook gateway (HMAC verify, dedupe), reconciliation poller (the API is truth, webhooks are notifications), event bus with consumer-group semantics |
| Detection | `detection/` | Recoverability scoring (hard failures never pursued) + dual-EWMA degradation monitor per method × issuer cell |
| Diagnosis | `diagnosis/` | Claude structured-output diagnosis over a PII-free evidence pack, deterministic rule fallback on any failure |
| Decision + Compliance | `policy/` | EV ranking of interventions (negative-EV cases never pursued) filtered by policy-as-code compliance incl. e-mandate rules and a daily action budget |
| Execution | `workflows/flow.py` | Bounded playbooks behind the action gate; blocked steps defer, actuator failures back off, dry-run mode |
| Learning | `learning/bandit.py` | Per-segment channel bandit; improves recovery across the batch, can never relax a rule |
| Communication | `comms/` | LLM-drafted messages gated by a deterministic compliance lint; bounded Hinglish voice agent |
| Actuators | `actuators/razorpay_client.py` | Payment Links with idempotent reference IDs, retry/backoff, circuit breaker |
| Memory | `domain/`, `memory/` | Case lifecycle state machine; Customer-360 (cross-case caps, permanent opt-outs, channel affinity) |
| Audit + Storage | `audit/`, `storage/` | Tamper-evident hash chain, in-memory and SQLite (restart-proof) |
| Evaluation | `evaluation/` | Scenario generator, persona simulator, holdout threshold tuning, batch runner with baselines, failure demo |
| Dashboard | `dashboard/` | Zero-dependency HTML report: KPI tiles, quartile learning curve, per-case audit timelines |

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

The remaining items are backend swaps behind interfaces that already
exist and are tested: Temporal for the flow loop (its semantics are
clock-injected, so they transfer unchanged), Redis Streams behind
`InMemoryBus`, Postgres behind the SQLite stores, a telephony adapter
behind the voice agent's responder, and OpenTelemetry spans over the
audit stages.
