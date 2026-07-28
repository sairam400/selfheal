"""Tests for the sandboxed subprocess executor.

These exercise real subprocess execution (no network involved -- just the
local Python interpreter running a temp script), which is the most faithful
way to verify timeout and working-directory behavior.
"""

from __future__ import annotations

from selfheal.executor import run_script


def test_run_script_captures_stdout_on_success(tmp_path):
    result = run_script("print('hello from script')", cwd=tmp_path, timeout=10)

    assert result.succeeded is True
    assert result.exit_code == 0
    assert "hello from script" in result.stdout
    assert result.timed_out is False


def test_run_script_captures_traceback_on_failure(tmp_path):
    result = run_script("raise ValueError('boom')", cwd=tmp_path, timeout=10)

    assert result.succeeded is False
    assert result.exit_code == 1
    assert "ValueError: boom" in result.stderr


def test_run_script_kills_on_timeout(tmp_path):
    result = run_script("import time; time.sleep(5)", cwd=tmp_path, timeout=1)

    assert result.succeeded is False
    assert result.timed_out is True
    assert result.exit_code is None


def test_run_script_runs_in_given_cwd(tmp_path):
    marker = tmp_path / "marker.txt"
    code = "from pathlib import Path; Path('marker.txt').write_text('present')"

    run_script(code, cwd=tmp_path, timeout=10)

    assert marker.exists()
    assert marker.read_text() == "present"
