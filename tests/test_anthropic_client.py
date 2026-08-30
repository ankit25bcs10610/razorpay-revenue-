from types import SimpleNamespace

import pytest

from revrecover.diagnosis.anthropic_client import DEFAULT_MODEL, AnthropicDiagnosisClient
from revrecover.diagnosis.diagnostician import DIAGNOSIS_SCHEMA


class StubMessages:
    def __init__(self, blocks):
        self.blocks = blocks
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(content=self.blocks)


def make_stub(blocks):
    messages = StubMessages(blocks)
    return SimpleNamespace(messages=messages), messages


def test_sends_structured_output_request_with_schema_and_model():
    sdk, messages = make_stub([SimpleNamespace(type="text", text="{}")])
    client = AnthropicDiagnosisClient(sdk_client=sdk)
    client.complete(system="sys", user="{\"a\":1}", schema=DIAGNOSIS_SCHEMA)

    assert messages.kwargs["model"] == DEFAULT_MODEL
    assert messages.kwargs["system"] == "sys"
    assert messages.kwargs["output_config"]["format"]["type"] == "json_schema"
    assert messages.kwargs["output_config"]["format"]["schema"] == DIAGNOSIS_SCHEMA
    assert messages.kwargs["messages"] == [{"role": "user", "content": "{\"a\":1}"}]


def test_returns_text_of_first_text_block():
    sdk, _ = make_stub(
        [
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text='{"cause": "x"}'),
        ]
    )
    client = AnthropicDiagnosisClient(sdk_client=sdk)
    assert client.complete(system="s", user="u", schema={}) == '{"cause": "x"}'


def test_raises_when_no_text_block_present():
    sdk, _ = make_stub([SimpleNamespace(type="thinking", thinking="")])
    client = AnthropicDiagnosisClient(sdk_client=sdk)
    with pytest.raises(ValueError, match="no text block"):
        client.complete(system="s", user="u", schema={})
