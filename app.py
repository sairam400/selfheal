"""Custom web demo for selfheal: a small FastAPI backend + vanilla JS frontend.

No Gradio here -- this is a hand-built UI so the agent's generate/run/fix
loop can be shown as a live activity feed with an animated status avatar.
Each attempt streams to the browser as newline-delimited JSON as soon as
it happens.

Run with ``python app.py`` and open http://127.0.0.1:7860.
"""

from __future__ import annotations

import json
import os
import queue
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from selfheal import run
from selfheal.config import DEFAULT_MAX_ATTEMPTS, DEFAULT_TIMEOUT_SECONDS, get_api_key
from selfheal.models import Attempt

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="selfheal")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class RunRequest(BaseModel):
    """Payload the frontend posts to kick off an agent run."""

    task: str
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    confirm: bool = False


def _event(kind: str, **payload: object) -> str:
    """Serialize one newline-delimited JSON event for the activity feed."""
    return json.dumps({"type": kind, **payload}) + "\n"


def _attempt_status(attempt: Attempt) -> str:
    if attempt.succeeded:
        return "success"
    if attempt.timed_out:
        return "timeout"
    return "error"


def _stream(req: RunRequest) -> Iterator[str]:
    """Run the agent loop and yield one JSON event per state change.

    Runs the (blocking) agent loop on a background thread and relays each
    attempt to the caller as soon as it happens via a thread-safe queue, so
    the browser sees the loop unfold live instead of waiting for it to
    finish.
    """
    if not req.task.strip():
        yield _event("error", message="Please enter a task.")
        return
    if not req.confirm:
        yield _event("error", message="Please check the confirmation box before running.")
        return
    try:
        get_api_key()
    except RuntimeError as exc:
        yield _event("error", message=str(exc))
        return

    events: queue.Queue[tuple[str, dict]] = queue.Queue()
    attempt_count = 0
    result_holder: dict = {}

    def on_attempt(attempt: Attempt) -> None:
        nonlocal attempt_count
        attempt_count += 1
        events.put(
            (
                "attempt",
                {
                    "attempt": attempt_count,
                    "status": _attempt_status(attempt),
                    "code": attempt.code,
                    "output": attempt.output,
                    "error": attempt.error,
                    "exit_code": attempt.exit_code,
                },
            )
        )
        if not attempt.succeeded and attempt_count < req.max_attempts:
            events.put(("thinking", {"message": "Reading the traceback and rewriting the code..."}))

    def do_run(workdir: str) -> None:
        try:
            result_holder["result"] = run(
                req.task,
                max_attempts=req.max_attempts,
                timeout=req.timeout,
                workdir=workdir,
                on_attempt=on_attempt,
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI, not a crash
            result_holder["exception"] = exc
        finally:
            events.put(("__done__", {}))

    with tempfile.TemporaryDirectory(prefix="selfheal_demo_") as workdir:
        thread = threading.Thread(target=do_run, args=(workdir,))
        thread.start()

        yield _event("thinking", message="Writing code for your task...")
        while True:
            kind, payload = events.get()
            if kind == "__done__":
                break
            yield _event(kind, **payload)
        thread.join()

        if "exception" in result_holder:
            yield _event("error", message=str(result_holder["exception"]))
            return

        result = result_holder["result"]
        yield _event("done", succeeded=result.succeeded, attempts=result.num_attempts)


@app.get("/")
def index() -> FileResponse:
    """Serve the single-page frontend."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/run")
def api_run(req: RunRequest) -> StreamingResponse:
    """Stream the agent loop's progress as newline-delimited JSON."""
    return StreamingResponse(_stream(req), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn

    # HF Spaces (and most PaaS hosts) set HOST=0.0.0.0 and PORT; default to
    # localhost-only for local development.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "7860"))
    uvicorn.run(app, host=host, port=port)
