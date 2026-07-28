"""Gradio web demo for selfheal.

Shows each generate-run-fix attempt as an expandable step: the generated
code, its output or error, and (if it failed) the fix that follows.
Deployable as-is to Hugging Face Spaces (``python app.py`` launches it).
"""

from __future__ import annotations

import tempfile
import threading

import gradio as gr

from selfheal import run
from selfheal.config import DEFAULT_MAX_ATTEMPTS, DEFAULT_TIMEOUT_SECONDS
from selfheal.models import Attempt

SAFETY_NOTE = """\
**Safety note:** the script Claude writes for your task is executed on the
server running this demo, inside a subprocess with a timeout and confined to
a temporary working directory. Do not paste tasks you wouldn't want run by
an automated script. See the project README for full details.
"""


def _attempt_markdown(attempt: Attempt, attempt_num: int) -> str:
    status = "SUCCESS" if attempt.succeeded else ("TIMED OUT" if attempt.timed_out else "FAILED")
    parts = [f"### Attempt {attempt_num}: {status}", "```python", attempt.code, "```"]
    if attempt.output:
        parts += ["**stdout:**", "```", attempt.output, "```"]
    if attempt.error:
        parts += ["**stderr:**", "```", attempt.error, "```"]
    return "\n".join(parts)


def run_task(task: str, max_attempts: int, timeout: int, confirm: bool):
    """Run the selfheal agent loop for the Gradio UI and stream attempt logs.

    Args:
        task: Plain-English task description from the textbox.
        max_attempts: Max generate-run-fix cycles, from the slider.
        timeout: Per-attempt execution timeout in seconds, from the slider.
        confirm: Whether the "I understand" checkbox is ticked.

    Yields:
        Updated markdown log after each attempt completes.
    """
    if not task.strip():
        yield "Please enter a task."
        return
    if not confirm:
        yield (
            "Please check the confirmation box first. Generated code executes "
            "on the server -- review the safety note above."
        )
        return

    log_sections: list[str] = []
    with tempfile.TemporaryDirectory(prefix="selfheal_demo_") as workdir:

        def on_attempt(attempt: Attempt) -> None:
            log_sections.append(_attempt_markdown(attempt, len(log_sections) + 1))

        result_holder = {}

        def do_run():
            result_holder["result"] = run(
                task,
                max_attempts=int(max_attempts),
                timeout=int(timeout),
                workdir=workdir,
                on_attempt=on_attempt,
            )

        # Run the blocking agent loop on a background thread and poll
        # log_sections so we can yield incremental updates to the UI.
        thread = threading.Thread(target=do_run)
        thread.start()
        last_count = 0
        while thread.is_alive():
            thread.join(timeout=0.5)
            if len(log_sections) != last_count:
                last_count = len(log_sections)
                yield "\n\n---\n\n".join(log_sections)
        thread.join()

        result = result_holder["result"]
        final = "\n\n---\n\n".join(log_sections)
        summary = (
            f"\n\n---\n\n## {'Succeeded' if result.succeeded else 'Gave up'} "
            f"after {result.num_attempts} attempt(s)"
        )
        yield final + summary


with gr.Blocks(title="selfheal") as demo:
    gr.Markdown("# selfheal")
    gr.Markdown(
        "Describe a task in plain English. Claude writes a Python script, "
        "runs it, and fixes its own errors until it works or hits the "
        "attempt limit."
    )
    gr.Markdown(SAFETY_NOTE)

    task_input = gr.Textbox(
        label="Task",
        placeholder="e.g. count the number of words in all .txt files in the current directory",
        lines=2,
    )
    with gr.Row():
        max_attempts_input = gr.Slider(
            minimum=1, maximum=8, step=1, value=DEFAULT_MAX_ATTEMPTS, label="Max attempts"
        )
        timeout_input = gr.Slider(
            minimum=5, maximum=120, step=5, value=DEFAULT_TIMEOUT_SECONDS, label="Timeout (seconds)"
        )
    confirm_input = gr.Checkbox(
        label="I understand this executes generated Python code on the server."
    )
    run_button = gr.Button("Run", variant="primary")
    output_markdown = gr.Markdown()

    run_button.click(
        fn=run_task,
        inputs=[task_input, max_attempts_input, timeout_input, confirm_input],
        outputs=output_markdown,
    )

if __name__ == "__main__":
    demo.launch()
