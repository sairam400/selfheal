"""Sandboxed execution of generated Python scripts.

Generated code is always run as an isolated ``python`` subprocess -- never
via ``exec``/``eval`` in-process -- so a runaway or malicious script can't
touch selfheal's own process state, and can be bounded by a timeout.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import DEFAULT_TIMEOUT_SECONDS


@dataclass
class ExecutionResult:
    """Raw result of running a script in a subprocess.

    Attributes:
        stdout: Captured standard output.
        stderr: Captured standard error (includes tracebacks on failure).
        exit_code: Process exit code, or ``None`` if the process timed out.
        timed_out: Whether the process was killed for exceeding the timeout.
    """

    stdout: str
    stderr: str
    exit_code: int | None
    timed_out: bool

    @property
    def succeeded(self) -> bool:
        """True if the process exited cleanly with code 0."""
        return self.exit_code == 0 and not self.timed_out


def run_script(
    code: str,
    *,
    cwd: str | Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> ExecutionResult:
    """Execute a Python script in a subprocess and capture its result.

    The script is written to a temporary file and run with the current
    interpreter (``sys.executable``), bounded to ``cwd`` as its working
    directory and killed if it exceeds ``timeout`` seconds.

    Args:
        code: The full Python source to execute.
        cwd: Working directory the subprocess is confined to. This is the
            directory any relative file operations in the generated code
            will resolve against.
        timeout: Maximum seconds to let the script run before it is killed.

    Returns:
        An :class:`ExecutionResult` with stdout, stderr, exit code, and
        whether the process timed out.
    """
    cwd = Path(cwd)
    cwd.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8",
    ) as tmp_file:
        tmp_file.write(code)
        script_path = Path(tmp_file.name)

    try:
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return ExecutionResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        stderr += f"\n[selfheal] Script timed out after {timeout} seconds."
        return ExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=None,
            timed_out=True,
        )
    finally:
        script_path.unlink(missing_ok=True)
