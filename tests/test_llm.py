"""Tests for prompt/response handling in selfheal.llm.

The Anthropic SDK itself is mocked here so these run fully offline.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from selfheal.llm import ClaudeClient, extract_code


def test_extract_code_pulls_fenced_python_block():
    text = "Here you go:\n```python\nprint('hi')\n```\nDone."
    assert extract_code(text) == "print('hi')"


def test_extract_code_handles_bare_fence():
    text = "```\nprint('hi')\n```"
    assert extract_code(text) == "print('hi')"


def test_extract_code_falls_back_to_raw_text_without_fence():
    text = "  print('hi')  "
    assert extract_code(text) == "print('hi')"


def _make_response(text: str) -> MagicMock:
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    return response


@patch("selfheal.llm.anthropic.Anthropic")
def test_generate_script_sends_task_and_extracts_code(mock_anthropic_cls, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_instance = mock_anthropic_cls.return_value
    mock_instance.messages.create.return_value = _make_response("```python\nprint(1)\n```")

    client = ClaudeClient(model="claude-test")
    code = client.generate_script("print the number 1")

    assert code == "print(1)"
    _, kwargs = mock_instance.messages.create.call_args
    assert kwargs["model"] == "claude-test"
    assert "print the number 1" in kwargs["messages"][0]["content"]


@patch("selfheal.llm.anthropic.Anthropic")
def test_fix_script_includes_code_and_error_in_prompt(mock_anthropic_cls, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_instance = mock_anthropic_cls.return_value
    mock_instance.messages.create.return_value = _make_response("```python\nprint(2)\n```")

    client = ClaudeClient(model="claude-test")
    code = client.fix_script("task", "print(1/0)", "ZeroDivisionError")

    assert code == "print(2)"
    _, kwargs = mock_instance.messages.create.call_args
    prompt = kwargs["messages"][0]["content"]
    assert "print(1/0)" in prompt
    assert "ZeroDivisionError" in prompt
