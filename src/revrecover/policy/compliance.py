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


@dataclass
class ActionBudget:
    """Per-day action counter shared across cases (the autonomy budget)."""

    _by_day: dict = field(default_factory=dict)

    def record(self, at: datetime) -> None:
        key = at.date()
        self._by_day[key] = self._by_day.get(key, 0) + 1

    def count(self, at: datetime) -> int:
        return self._by_day.get(at.date(), 0)


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
    daily_action_budget: int
    max_representments: int
    pre_debit_notice_hours: int

    @classmethod
    def from_yaml(cls, path: Path | str) -> ComplianceEngine:
        raw = yaml.safe_load(Path(path).read_text())
        contact, payments, autonomy = raw["contact"], raw["payments"], raw["autonomy"]
        mandate = raw["mandate_retry"]
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
            daily_action_budget=autonomy["daily_action_budget"],
            max_representments=mandate["max_representments"],
            pre_debit_notice_hours=mandate["require_pre_debit_notification_hours"],
        )

    def check(
        self,
        action: ProposedAction,
        *,
        case,
        contact_history: list[datetime],
        now: datetime,
        kill_switch: bool = False,
        actions_today: int = 0,
        retries_so_far: int = 0,
    ) -> Decision:
        if kill_switch:
            return Decision(allowed=False, failed_checks=["kill_switch"])
        if action.kind is ActionKind.ESCALATE:
            return Decision(allowed=True)

        failed: list[str] = []
        if actions_today >= self.daily_action_budget:
            failed.append("daily_action_budget")
        if case.attempts >= self.max_attempts_per_case:
            failed.append("max_attempts_per_case")
        if action.kind is ActionKind.RETRY:
            if case.error_code in self.never_retry_codes:
                failed.append("never_retry_code")
            failed.extend(
                self._mandate_checks(case, contact_history, now, retries_so_far)
            )
        if action.kind in CONTACT_KINDS:
            failed.extend(self._contact_checks(contact_history, now))

        return Decision(
            allowed=not failed,
            failed_checks=failed,
            requires_approval=case.amount_inr >= self.hitl_amount_threshold_inr,
        )

    def _mandate_checks(
        self, case, contact_history: list[datetime], now: datetime, retries_so_far: int
    ) -> list[str]:
        # RBI e-mandate rules apply to recurring (subscription) charges only:
        # a debit needs prior notice, and representments are capped.
        if case.case_type.value != "subscription_failure":
            return []
        failed: list[str] = []
        if retries_so_far >= self.max_representments:
            failed.append("max_representments")
        notice = timedelta(hours=self.pre_debit_notice_hours)
        if not any(now - contact >= notice for contact in contact_history):
            failed.append("pre_debit_notification")
        return failed

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
