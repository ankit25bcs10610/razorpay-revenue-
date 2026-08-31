"""RecoveryService: the wired end-to-end pipeline.

gateway intake -> event bus -> worker -> full recovery flow, sharing one
audit chain (SQLite in production shape), one Customer-360 store (opt-outs
and caps hold across cases), and one daily action budget. Customer
responses come from an injectable persona resolver — the demo default is
deterministic per customer; a live deployment replaces it with real
webhook-driven responses under a durable workflow runtime.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from revrecover.domain.models import Case
from revrecover.evaluation.harness import Persona, Scenario
from revrecover.gateway.bus import InMemoryBus, case_from_payload, case_to_payload
from revrecover.memory.customer360 import Customer360
from revrecover.policy.compliance import ActionBudget, ComplianceEngine
from revrecover.workflows.flow import CaseResult, run_case

_DEMO_PERSONAS = [
    Persona.COOPERATIVE,
    Persona.NEEDS_REMINDER,
    Persona.SALARY_CYCLE,
    Persona.PROMISE_BREAKER,
    Persona.DISPUTER,
    Persona.NEVER_PAYER,
]


def demo_persona(case: Case) -> Persona:
    """Deterministic per customer: same customer, same behavior."""
    return random.Random(case.customer_id).choice(_DEMO_PERSONAS)


@dataclass
class RecoveryService:
    engine: ComplianceEngine
    audit: Any  # AuditChain-shaped: append / verify / records_for_case
    bus: InMemoryBus = field(default_factory=InMemoryBus)
    customer360: Customer360 = field(default_factory=Customer360)
    budget: ActionBudget = field(default_factory=ActionBudget)
    persona_for: Callable[[Case], Persona] = demo_persona
    stream: str = "cases"
    group: str = "recovery"
    results: list[CaseResult] = field(default_factory=list)

    def enqueue(self, case: Case) -> None:
        self.bus.publish(self.stream, case_to_payload(case))

    def process_pending(self) -> list[CaseResult]:
        results: list[CaseResult] = []

        def handle(payload: dict) -> None:
            case = case_from_payload(payload)
            scenario = Scenario(case=case, persona=self.persona_for(case))
            results.append(
                run_case(
                    scenario,
                    engine=self.engine,
                    audit=self.audit,
                    budget=self.budget,
                    customer360=self.customer360,
                )
            )

        self.bus.consume(self.stream, group=self.group, handler=handle)
        self.results.extend(results)
        return results

    def render_dashboard(self) -> str:
        from revrecover.dashboard.live import render_live

        return render_live(audit=self.audit, results=self.results)
