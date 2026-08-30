.PHONY: test demo

test:
	uv run pytest

demo:
	uv run python -m revrecover.evaluation.batch
