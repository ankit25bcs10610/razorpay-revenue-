"""Deterministic policy-as-code compliance engine.

Compliance is a hard filter, never a preference weight: it runs before EV
ranking and again at execution time inside the Action Gate. Escalating to a
human is always compliant — the escape hatch must never be blockable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml


class ActionKind(str, Enum):
    RETRY = "retry"
    MESSAGE = "message"
    VOICE_CALL = "voice_call"
    ESCALATE = "escalate"


class Channel(str, Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"
    IN_APP = "in_app"
    VOICE = "voice"


CONTACT_KINDS = frozenset({ActionKind.MESSAGE, ActionKind.VOICE_CALL})


@dataclass(frozen=True)
class ProposedAction:
    kind: ActionKind
    channel: Channel | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    failed_checks: list[str] = field(default_factory=list)
    requires_approval: bool = False


@dataclass(frozen=True)
class ComplianceEngine:
    quiet_start: time
    quiet_end: time
    tz: ZoneInfo
    max_attempts_per_case: int
    max_contacts_per_week: int
    min_gap_hours: int
    never_retry_codes: frozenset[str]
    hitl_amount_threshold_inr: int

    @classmethod
    def from_yaml(cls, path: Path | str) -> "ComplianceEngine":
        raw = yaml.safe_load(Path(path).read_text())
        contact, payments, autonomy = raw["contact"], raw["payments"], raw["autonomy"]
        quiet = contact["quiet_hours"]
        return cls(
            quiet_start=time.fromisoformat(quiet["start"]),
            quiet_end=time.fromisoformat(quiet["end"]),
            tz=ZoneInfo(quiet["tz"]),
            max_attempts_per_case=contact["max_attempts_per_case"],
            max_contacts_per_week=contact["max_contacts_per_customer_per_week"],
            min_gap_hours=contact["min_gap_between_contacts_hours"],
            never_retry_codes=frozenset(payments["never_retry_codes"]),
            hitl_amount_threshold_inr=autonomy["hitl_amount_threshold_inr"],
        )

    def check(
        self,
        action: ProposedAction,
        *,
        case,
        contact_history: list[datetime],
        now: datetime,
        kill_switch: bool = False,
    ) -> Decision:
        if kill_switch:
            return Decision(allowed=False, failed_checks=["kill_switch"])
        if action.kind is ActionKind.ESCALATE:
            return Decision(allowed=True)

        failed: list[str] = []
        if case.attempts >= self.max_attempts_per_case:
            failed.append("max_attempts_per_case")
        if action.kind is ActionKind.RETRY and case.error_code in self.never_retry_codes:
            failed.append("never_retry_code")
        if action.kind in CONTACT_KINDS:
            failed.extend(self._contact_checks(contact_history, now))

        return Decision(
            allowed=not failed,
            failed_checks=failed,
            requires_approval=case.amount_inr >= self.hitl_amount_threshold_inr,
        )

    def _contact_checks(
        self, contact_history: list[datetime], now: datetime
    ) -> list[str]:
        failed: list[str] = []
        local = now.astimezone(self.tz).time()
        # Quiet window spans midnight (e.g. 21:00 -> 09:00).
        in_quiet = (
            local >= self.quiet_start or local < self.quiet_end
            if self.quiet_start > self.quiet_end
            else self.quiet_start <= local < self.quiet_end
        )
        if in_quiet:
            failed.append("quiet_hours")
        week_ago = now - timedelta(days=7)
        if sum(1 for c in contact_history if c >= week_ago) >= self.max_contacts_per_week:
            failed.append("max_contacts_per_week")
        min_gap = timedelta(hours=self.min_gap_hours)
        if any(now - c < min_gap for c in contact_history):
            failed.append("min_gap_between_contacts")
        return failed
