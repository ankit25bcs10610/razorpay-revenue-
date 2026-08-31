.PHONY: test demo serve dashboard failure-demo sweep

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
