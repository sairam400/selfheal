"""Shared fixtures for offline tests.

No test in this suite makes a real network call: Anthropic requests go
through :class:`FakeClaudeClient`, and where subprocess execution needs to
be controlled deterministically, ``selfheal.agent.run_script`` is monkeypatched.
"""

from __future__ import annotations

import pytest

from selfheal.executor import ExecutionResult


class FakeClaudeClient:
    """Stand-in for :class:`selfheal.llm.ClaudeClient` that returns canned code.

    ``fix_scripts`` is consumed in order: the first call to ``fix_script``
    returns ``fix_scripts[0]``, the second returns ``fix_scripts[1]``, etc.
    """

    def __init__(self, initial_script: str, fix_scripts: list[str] | None = None) -> None:
        self.initial_script = initial_script
        self.fix_scripts = list(fix_scripts or [])
        self.generate_calls: list[str] = []
        self.fix_calls: list[tuple[str, str, str]] = []

    def generate_script(self, task: str) -> str:
        self.generate_calls.append(task)
        return self.initial_script

    def fix_script(self, task: str, code: str, error: str) -> str:
        self.fix_calls.append((task, code, error))
        return self.fix_scripts.pop(0)


@pytest.fixture
def make_execution_result():
    """Factory for :class:`ExecutionResult` objects in test bodies."""

    def _make(
        *, stdout: str = "", stderr: str = "", exit_code: int | None = 0, timed_out: bool = False
    ) -> ExecutionResult:
        return ExecutionResult(
            stdout=stdout, stderr=stderr, exit_code=exit_code, timed_out=timed_out
        )

    return _make
