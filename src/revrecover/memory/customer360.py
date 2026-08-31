"""Customer-360 store: what the agent knows about a customer across cases.

Feeds the compliance engine's frequency caps with the customer's real
cross-case contact history, remembers opt-outs permanently (an opt-out in
one case forbids contact in every later case), and keeps a channel
affinity hint from past recoveries. In-memory here; the interface is what
a Postgres-backed implementation replaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from revrecover.policy.compliance import Channel


@dataclass
class Customer360:
    _contacts: dict[str, list[datetime]] = field(default_factory=dict)
    _opt_outs: set[str] = field(default_factory=set)
    _affinity: dict[str, Channel] = field(default_factory=dict)

    def record_contact(self, customer_id: str, at: datetime) -> None:
        self._contacts.setdefault(customer_id, []).append(at)

    def contacts_for(self, customer_id: str) -> list[datetime]:
        return list(self._contacts.get(customer_id, []))

    def record_opt_out(self, customer_id: str) -> None:
        self._opt_outs.add(customer_id)

    def has_opted_out(self, customer_id: str) -> bool:
        return customer_id in self._opt_outs

    def record_recovery(self, customer_id: str, channel: Channel | None) -> None:
        if channel is not None:
            self._affinity[customer_id] = channel

    def preferred_channel_hint(self, customer_id: str) -> Channel | None:
        return self._affinity.get(customer_id)
