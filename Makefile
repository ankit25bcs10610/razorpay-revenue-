.PHONY: test demo serve

test:
	uv run pytest

demo:
	uv run python -m revrecover.evaluation.batch

serve:
	uv run python -m revrecover.gateway
