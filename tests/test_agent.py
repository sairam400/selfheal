"""Tests for the core generate-run-fix loop in selfheal.agent."""

from __future__ import annotations

import selfheal.agent as agent_module
from selfheal.agent import run
from tests.conftest import FakeClaudeClient

GOOD_CODE = "print('hello')"
BAD_CODE = "raise ValueError('boom')"
FIXED_CODE = "print('fixed')"


def test_run_succeeds_on_first_attempt(monkeypatch, make_execution_result):
    monkeypatch.setattr(
        agent_module,
        "run_script",
        lambda code, cwd, timeout: make_execution_result(stdout="hello\n", exit_code=0),
    )
    client = FakeClaudeClient(initial_script=GOOD_CODE)

    result = run("say hello", client=client)

    assert result.succeeded is True
    assert result.final_code == GOOD_CODE
    assert result.result_output == "hello\n"
    assert result.num_attempts == 1
    assert len(client.fix_calls) == 0


def test_run_fails_then_succeeds(monkeypatch, make_execution_result):
    """The headline scenario: attempt 1 errors, attempt 2 (the fix) succeeds."""
    responses = [
        make_execution_result(stderr="ValueError: boom", exit_code=1),
        make_execution_result(stdout="fixed\n", exit_code=0),
    ]
    monkeypatch.setattr(
        agent_module,
        "run_script",
        lambda code, cwd, timeout: responses.pop(0),
    )
    client = FakeClaudeClient(initial_script=BAD_CODE, fix_scripts=[FIXED_CODE])

    result = run("do a thing", client=client, max_attempts=4)

    assert result.succeeded is True
    assert result.num_attempts == 2
    assert result.final_code == FIXED_CODE
    assert result.attempts[0].succeeded is False
    assert result.attempts[0].error == "ValueError: boom"
    assert result.attempts[1].succeeded is True
    assert len(client.fix_calls) == 1
    fix_task, fix_code, fix_error = client.fix_calls[0]
    assert fix_task == "do a thing"
    assert fix_code == BAD_CODE
    assert fix_error == "ValueError: boom"


def test_run_gives_up_after_max_attempts(monkeypatch, make_execution_result):
    monkeypatch.setattr(
        agent_module,
        "run_script",
        lambda code, cwd, timeout: make_execution_result(stderr="still broken", exit_code=1),
    )
    client = FakeClaudeClient(
        initial_script=BAD_CODE,
        fix_scripts=[BAD_CODE, BAD_CODE],  # enough fixes for attempts 2 and 3
    )

    result = run("do a thing", client=client, max_attempts=3)

    assert result.succeeded is False
    assert result.num_attempts == 3
    assert result.result_output == "still broken"
    # A fix is only requested after a failed attempt that isn't the last one.
    assert len(client.fix_calls) == 2


def test_on_attempt_callback_invoked_per_attempt(monkeypatch, make_execution_result):
    responses = [
        make_execution_result(stderr="boom", exit_code=1),
        make_execution_result(stdout="ok\n", exit_code=0),
    ]
    monkeypatch.setattr(
        agent_module,
        "run_script",
        lambda code, cwd, timeout: responses.pop(0),
    )
    client = FakeClaudeClient(initial_script=BAD_CODE, fix_scripts=[GOOD_CODE])

    seen = []
    run("do a thing", client=client, max_attempts=4, on_attempt=seen.append)

    assert len(seen) == 2
    assert seen[0].succeeded is False
    assert seen[1].succeeded is True


def test_run_passes_workdir_and_timeout_to_executor(monkeypatch, make_execution_result, tmp_path):
    captured = {}

    def fake_run_script(code, cwd, timeout):
        captured["cwd"] = cwd
        captured["timeout"] = timeout
        return make_execution_result(exit_code=0)

    monkeypatch.setattr(agent_module, "run_script", fake_run_script)
    client = FakeClaudeClient(initial_script=GOOD_CODE)

    run("task", client=client, workdir=tmp_path, timeout=7)

    assert captured["cwd"] == tmp_path
    assert captured["timeout"] == 7
