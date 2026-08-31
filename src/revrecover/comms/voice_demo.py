"""Hinglish voice call demo:  make voice-demo

Prints a full bounded recovery call. With ANTHROPIC_API_KEY set the
agent's lines come from Claude (threat-screened, script-bounded); without
it, the deterministic Hinglish script speaks. The customer is a scripted
promise-then-pay persona.
"""

import os
from datetime import UTC, datetime

from revrecover.comms.voice import VoiceRecoveryAgent
from revrecover.domain.models import Case, CaseType

_CUSTOMER_LINES = [
    "haan boliye, kaun?",
    "abhi thoda busy hoon, kal pakka kar dunga",
    "theek hai bhai, abhi link se payment kar diya, done",
]


def main() -> None:
    llm = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        from revrecover.diagnosis.anthropic_client import AnthropicDiagnosisClient

        llm = AnthropicDiagnosisClient()

    case = Case(
        case_id="case_voice_demo",
        case_type=CaseType.OVERDUE_INVOICE,
        customer_id="cust_voice",
        amount_inr=15000,
        error_code="OVERDUE",
        detected_at=datetime.now(UTC),
    )
    agent = VoiceRecoveryAgent(llm)
    outcome = agent.call(case, lambda line, turn: _CUSTOMER_LINES[min(turn, 2)])

    mode = "Claude-voiced" if llm else "scripted"
    print(f"RevRecover — Hinglish voice recovery call ({mode})")
    print("=" * 60)
    for turn in outcome.transcript:
        speaker = "AGENT   " if turn.speaker == "agent" else "CUSTOMER"
        print(f"  {speaker} | {turn.text}")
    print("=" * 60)
    print(f"result: {outcome.result} · turns capped at {agent.max_turns}")


if __name__ == "__main__":
    main()
