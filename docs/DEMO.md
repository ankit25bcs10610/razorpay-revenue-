# 5-Minute Pitch — Demo Script

Target: judges see the full loop, the bounds, and the honest number — in
this order. Every command below is real; rehearse against a fresh clone.

## 0:00–0:40 — The problem (talking head, one slide)

Revenue loss is gradual: a payment fails, a subscription halts, an invoice
quietly ages. No single failure is worth a human's attention, so the money
leaks. RevRecover closes the loop — detect, diagnose, decide, act, measure —
with every money action explainable, bounded, and gated.

## 0:40–1:40 — The measured number (terminal)

```bash
make demo
```

Talk over the output:
- First line: the pursue threshold was **tuned on a 100-case holdout,
  never on this batch** — the headline can't tune itself.
- ₹18.6L at risk across 400 seeded cases → **₹9.1L recovered (48.8%)
  with learning on**, vs 42.1% static and two baselines (do-nothing,
  naive retry-everything). Our number is *incremental*, not gross.
- Point at the **learning curve**: 43% → 52% → 54% across quartiles — the
  bandit discovers that business customers answer email, consumers answer
  WhatsApp, and it earns +₹1.25L over the static default on the same seed.
- Point at the honesty lines: never-payers make 100% impossible;
  **29 annoyance contacts** are reported as false-positive cost; stop
  reasons account for every one of the 400 cases.
- "Same seed, same report, on your machine — nothing here is cherry-picked."

## 1:40–2:40 — Live ingestion (terminal, two panes)

Pane 1: `make serve`. Pane 2: the three curls from the README:

1. Signed `payment.failed` webhook → `{"status":"accepted","case_id":...}`
2. Replay the same event → `{"status":"duplicate"}` — idempotency
3. Tamper one byte of the body → `401` — signature verification

"Webhooks are how Razorpay talks; the gateway verifies, dedupes, and turns
events into cases."

## 2:40–3:40 — Bounded autonomy (editor + test run)

- Open `policy/compliance.yaml`: quiet hours (RBI norms), attempt caps,
  never-retry codes, ₹50k human-approval threshold, kill switch.
- Run the stopping-rule tests by name:

```bash
uv run pytest tests/test_flow.py -k "never_a_fourth or opt_out or kill_switch" -v
```

"The agent stops after three attempts, honors an opt-out on the spot, and a
kill switch freezes everything. These aren't promises — they're tests."

## 3:40–4:30 — The LLM boundary + audit trail (editor)

- `diagnosis/diagnostician.py`: Claude diagnoses over a PII-free evidence
  pack; a hallucinated playbook, malformed JSON, or an API outage all fall
  back to the rule engine — show `test_unknown_playbook_from_llm_is_rejected`.
- `audit/chain.py`: hash-chained ledger. Show
  `test_verify_detects_tampered_payload` — edit one historical record, the
  chain breaks at that exact record. "A compliance officer can replay every
  decision, including the roads not taken."
- `make failure-demo`: an issuer outage hits mid-retry — ACT_FAILED lands
  in the audit chain, the agent backs off 24h, retries, recovers ₹4,999,
  chain intact. Failure handling, demonstrated, not claimed.
- `make dashboard` → open `dashboard.html`: KPI tiles, the learning curve,
  and click open one case card — the full DETECT → PLAN (with rejected
  alternatives and their EVs) → DECIDE → ACT → OUTCOME timeline with the
  compliance checks inline. This is the audit chain a human actually reads.

## 4:30–5:00 — Close

Built test-first (226 tests incl. property-based invariants, ~2s), designed to slot
into production shape: the intake seam becomes Redis Streams, the flow loop
becomes a Temporal workflow, the same clock-injected semantics throughout.
One loop, fully closed, honestly measured — that's the pitch.
