"""The demonstrated-failure scene:  make failure-demo

A payment case hits an issuer outage mid-retry. The agent audits the
failure, backs off, re-plans, and still recovers the money — on camera.
"""

from pathlib import Path

from revrecover.audit.chain import AuditChain
from revrecover.domain.models import Case, CaseType
from revrecover.evaluation.harness import BATCH_START, Persona, Scenario
from revrecover.policy.compliance import ActionKind, ComplianceEngine
from revrecover.workflows.flow import TransientActuatorError, run_case

POLICY = Path(__file__).parents[3] / "policy" / "compliance.yaml"


class IssuerOutageOnFirstRetry:
    def __init__(self):
        self.retry_calls = 0

    def __call__(self, action, case) -> None:
        if action.kind is ActionKind.RETRY:
            self.retry_calls += 1
            if self.retry_calls == 1:
                raise TransientActuatorError("issuer gateway 5xx: UPI/HDFC outage window")


def main() -> None:
    case = Case(
        case_id="case_outage_demo",
        case_type=CaseType.PAYMENT_FAILURE,
        customer_id="cust_demo",
        amount_inr=4999,
        error_code="ISSUER_UNAVAILABLE",
        detected_at=BATCH_START,
    )
    scenario = Scenario(case=case, persona=Persona.SALARY_CYCLE)
    audit = AuditChain()
    engine = ComplianceEngine.from_yaml(POLICY)

    result = run_case(scenario, engine=engine, audit=audit, executor=IssuerOutageOnFirstRetry())

    print("Issuer outage mid-retry — the agent's own audit trail:")
    print("=" * 60)
    for record in audit.records_for_case(case.case_id):
        summary = ", ".join(f"{k}={v}" for k, v in record.payload.items())
        print(f"  [{record.at:%d %b %H:%M}] {record.stage:<11} {summary}")
    print("=" * 60)
    print(
        f"outcome: {result.case.state.value} — recovered ₹{result.recovered_inr:,} "
        f"after {result.case.attempts} attempt(s), chain intact={audit.verify()[0]}"
    )


if __name__ == "__main__":
    main()
