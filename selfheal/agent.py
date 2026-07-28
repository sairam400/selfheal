"""The self-healing agent loop: generate, run, diagnose, fix, repeat."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .config import DEFAULT_MAX_ATTEMPTS, DEFAULT_MODEL, DEFAULT_TIMEOUT_SECONDS
from .executor import run_script
from .llm import ClaudeClient
from .models import Attempt, RunResult

# Called after each attempt with the Attempt that just completed, so callers
# (the CLI, the Gradio app) can stream progress instead of waiting for the
# whole loop to finish.
AttemptCallback = Callable[[Attempt], None]


def run(
    task: str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    workdir: str | Path = ".",
    model: str = DEFAULT_MODEL,
    on_attempt: AttemptCallback | None = None,
    client: ClaudeClient | None = None,
) -> RunResult:
    """Run the self-healing agent loop for a plain-English task.

    Claude writes a Python script for the task, the script is executed in a
    sandboxed subprocess, and if it fails, the code and traceback are fed
    back to Claude for a fix. This repeats until the script succeeds or
    ``max_attempts`` is reached.

    Args:
        task: Plain-English description of what the script should do.
        max_attempts: Maximum number of generate-run cycles before giving up.
        timeout: Seconds to allow each script execution before killing it.
        workdir: Directory the generated script is executed in; relative
            file operations in the script resolve against this path.
        model: Claude model id to use for generation.
        on_attempt: Optional callback invoked with each :class:`Attempt`
            immediately after it completes, useful for streaming UIs.
        client: Optional pre-built :class:`ClaudeClient`, primarily for
            testing. If omitted, one is constructed from ``model``.

    Returns:
        A :class:`RunResult` containing the final code, whether it
        succeeded, and the full history of attempts.
    """
    claude = client or ClaudeClient(model=model)
    attempts: list[Attempt] = []

    code = claude.generate_script(task)

    for attempt_num in range(1, max_attempts + 1):
        exec_result = run_script(code, cwd=workdir, timeout=timeout)
        attempt = Attempt(
            code=code,
            output=exec_result.stdout,
            error=exec_result.stderr,
            succeeded=exec_result.succeeded,
            exit_code=exec_result.exit_code,
            timed_out=exec_result.timed_out,
        )
        attempts.append(attempt)
        if on_attempt is not None:
            on_attempt(attempt)

        if attempt.succeeded:
            return RunResult(
                task=task,
                final_code=code,
                succeeded=True,
                attempts=attempts,
                result_output=attempt.output,
            )

        if attempt_num == max_attempts:
            break

        code = claude.fix_script(task, code, attempt.error)

    return RunResult(
        task=task,
        final_code=code,
        succeeded=False,
        attempts=attempts,
        result_output=attempts[-1].error if attempts else "",
    )
