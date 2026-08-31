"""Hinglish voice recovery agent over a simulated transcript channel.

The LLM may phrase the agent's next line; deterministic code owns the
call: a hard turn cap the model cannot extend, immediate opt-out honoring
with a closing apology and nothing after it, threat-screened lines that
fall back to the script, and deterministic classification of the
customer's reply. Swap the responder for a telephony adapter (Exotel /
Twilio) to go live — the loop doesn't change.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from revrecover.comms.drafter import DEFAULT_MERCHANT, contains_threats
from revrecover.diagnosis.diagnostician import LLMClient
from revrecover.domain.models import Case

_SAY_SCHEMA = {
    "type": "object",
    "properties": {"say": {"type": "string", "minLength": 1}},
    "required": ["say"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "You are a polite Hinglish (Hindi-English code-switch) payment reminder "
    "voice agent for {merchant}. One short spoken line per turn. Never "
    "pressure, never threaten, always respectful. Return JSON: {\"say\": ...}."
)

_OPT_OUT = ("stop", "mat karo", "mat call", "don't call", "unsubscribe")
_PAID = ("kar diya", "ho gaya", "done", "paid")
_PROMISE = ("kal", "kar dunga", "kar doonga", "pakka", "promise", "baad mein")

_CLOSING_LINE = (
    "Bilkul, maaf kijiye takleef ke liye. Hum aapko dobara call nahi "
    "karenge. Dhanyavaad!"
)


def _script_line(turn: int, case: Case, merchant: str) -> str:
    amount = f"₹{case.amount_inr:,}"
    if turn == 0:
        return (
            f"Namaste! Main {merchant} ki taraf se bol raha hoon. Aapka "
            f"{amount} ka payment pending hai — kya main madad kar sakta hoon?"
        )
    if turn == 1:
        return (
            f"Koi baat nahi, aap apne convenience se link par {amount} pay "
            "kar sakte hain. Kya aaj possible hoga?"
        )
    return (
        "Theek hai, main bas yaad dilane ke liye call kiya tha. Aap link se "
        "kabhi bhi pay kar sakte hain. Dhanyavaad!"
    )


def _classify(reply: str) -> str | None:
    lowered = reply.lower()
    if any(marker in lowered for marker in _OPT_OUT):
        return "opt_out"
    if any(marker in lowered for marker in _PAID):
        return "paid"
    if any(marker in lowered for marker in _PROMISE):
        return "promise_to_pay"
    return None


@dataclass(frozen=True)
class VoiceTurn:
    speaker: str  # "agent" | "customer"
    text: str


@dataclass(frozen=True)
class VoiceOutcome:
    transcript: list[VoiceTurn]
    result: str  # "paid" | "promise_to_pay" | "opt_out" | "no_resolution"


@dataclass
class VoiceRecoveryAgent:
    llm: LLMClient | None
    max_turns: int = 6
    merchant: str = DEFAULT_MERCHANT

    def call(
        self, case: Case, responder: Callable[[str, int], str]
    ) -> VoiceOutcome:
        transcript: list[VoiceTurn] = []
        for turn in range(self.max_turns):  # the model can never extend this
            line = self._agent_line(turn, case, transcript)
            transcript.append(VoiceTurn("agent", line))
            reply = responder(line, turn)
            transcript.append(VoiceTurn("customer", reply))
            result = _classify(reply)
            if result == "opt_out":
                transcript.append(VoiceTurn("agent", _CLOSING_LINE))
                return VoiceOutcome(transcript=transcript, result="opt_out")
            if result is not None:
                return VoiceOutcome(transcript=transcript, result=result)
        return VoiceOutcome(transcript=transcript, result="no_resolution")

    def _agent_line(self, turn: int, case: Case, transcript: list[VoiceTurn]) -> str:
        fallback = _script_line(turn, case, self.merchant)
        if self.llm is None:
            return fallback
        try:
            raw = self.llm.complete(
                system=_SYSTEM_PROMPT.replace("{merchant}", self.merchant),
                user=json.dumps(
                    {
                        "turn": turn,
                        "amount_inr": case.amount_inr,
                        "transcript": [(t.speaker, t.text) for t in transcript],
                    }
                ),
                schema=_SAY_SCHEMA,
            )
            line = json.loads(raw)["say"]
        except Exception:
            return fallback
        # Script bounds: the opening must identify the merchant, and no
        # line may contain pressure language — otherwise use the script.
        if contains_threats(line) or (turn == 0 and self.merchant not in line):
            return fallback
        return line
