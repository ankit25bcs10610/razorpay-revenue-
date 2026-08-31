# Simulator priors and their grounding

The persona simulator is frozen before every measured run, and this file
documents where its numbers come from. The priors are *directional* —
calibrated to the shape of published industry figures, not fitted to any
proprietary dataset — and that is exactly the claim the batch report
makes: honest relative measurement, not absolute forecasting.

## Persona mix (soft-failure cases)

| Persona | Share | Behavior | Grounding |
|---|---|---|---|
| Self-cure | 10% | Pays without any contact | Dunning literature consistently finds a self-recovery band around 8–15% of failed renewals; contacting these customers is pure annoyance cost, which the report counts |
| Cooperative | 25% | Pays on first touch | First-reminder response is the largest single recovery bucket in published dunning funnels |
| Needs reminder | 20% | Pays on the 2nd on-channel nudge | Multi-touch dunning sequences recover meaningfully beyond touch 1; effectiveness is channel-dependent (see below) |
| Salary cycle | 15% | Retry succeeds from attempt 2 | India-specific NSF pattern: month-end insufficient-funds failures clear after payday; smart retry timing is the standard mitigation |
| Promise breaker | 15% | Promises, breaks once, pays on follow-up | Collections practice: promises-to-pay convert well below 100% and need tracked follow-ups |
| Disputer | 5% | Opts out on first contact | Opt-out/complaint rates in outbound collection channels |
| Never-payer | 10% | Money is gone | Hard floor that makes 100% recovery impossible by construction |

Hard failure codes (blocked card, closed account, suspected fraud) are
always never-payers: money behind a blocked instrument does not come back,
and a simulator that pretends otherwise would inflate the headline.

## Channel preferences

Business customers prefer email (70/15/15 email/SMS/WhatsApp); consumers
prefer WhatsApp (60/25/15 WhatsApp/SMS/email). Nudge-sensitive personas
only engage on their preferred channel. This is the structure the learning
layer must discover; the split direction follows B2B-vs-B2C channel
engagement patterns reported by CRM/CPaaS vendors in India (WhatsApp
dominance in consumer messaging, email in B2B billing).

## Recoverability priors (scorer)

| Error code | P(recover) | Rationale |
|---|---|---|
| ISSUER_UNAVAILABLE / GATEWAY_TIMEOUT | 0.85 / 0.82 | Transient infrastructure failures mostly succeed on retry |
| INSUFFICIENT_FUNDS | 0.68 | Recoverable with timing + nudges (salary cycle) |
| OVERDUE invoice | 0.55 | B2B receivables respond to structured follow-up |
| CARD_EXPIRED | 0.50 | Needs customer action (update method) |
| SESSION_EXPIRED (checkout) | 0.25 | Cart recovery converts a minority of abandoners |
| Unknown codes | 0.30 | Conservative; routed to manual review |

Reference points: cart abandonment ~70% with single-digit-to-low-teens
recovery from reminder flows (Baymard Institute aggregates and ESP case
studies); involuntary-churn recovery rates for subscription dunning in the
50–70% band for well-tuned sequences (Recurly/Chargebee published
research); UPI/issuer transient failure retry success from RBI/NPCI outage
post-mortems being materially higher than customer-side failures.

## What this means for the headline number

The 400-case measured batch answers "does the agent's decision-making beat
do-nothing and naive-retry on a world with this documented shape?" — it
does, on every seed tested (`make sweep`). It does not claim to predict
any specific merchant's absolute recovery rate; the live test-mode loop
(`make live-demo`) exists precisely to show the same machinery on real
Razorpay rails.
