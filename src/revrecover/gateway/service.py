"""Demo intake: what the gateway hands cases to when run standalone.

Scores each incoming case and writes the DETECT record to the audit chain.
Full recovery execution against live webhooks needs the durable-workflow
runtime (real waits between attempts); until then the intake proves the
webhook -> case -> detection -> audit path end to end.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from revrecover.audit.chain import AuditChain
from revrecover.detection.scorer import score
from revrecover.domain.models import Case


@dataclass
class DemoIntake:
    audit: AuditChain
    cases: list[Case] = field(default_factory=list)

    def __call__(self, case: Case) -> None:
        assessment = score(case)
        self.audit.append(
            case_id=case.case_id,
            stage="DETECT",
            payload={
                "case_type": case.case_type.value,
                "error_code": case.error_code,
                "amount_inr": case.amount_inr,
                "p_recover": assessment.p_recover,
                "playbook": assessment.playbook,
                "pursue": assessment.pursue,
            },
            at=case.detected_at,
        )
        self.cases.append(case)
