.PHONY: test demo serve dashboard failure-demo sweep live-demo voice-demo demo-llm

test:
	uv run pytest

demo:
	uv run python -m revrecover.evaluation.batch

serve:
	uv run python -m revrecover.gateway

dashboard:
	uv run python -m revrecover.dashboard

failure-demo:
	uv run python -m revrecover.evaluation.failure_demo

sweep:
	uv run python -m revrecover.evaluation.sweep

live-demo:
	uv run python -m revrecover.actuators.live_loop

voice-demo:
	uv run python -m revrecover.comms.voice_demo

demo-llm:
	uv run python -m revrecover.evaluation.llm_demo
