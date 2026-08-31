.PHONY: test demo serve dashboard

test:
	uv run pytest

demo:
	uv run python -m revrecover.evaluation.batch

serve:
	uv run python -m revrecover.gateway

dashboard:
	uv run python -m revrecover.dashboard
