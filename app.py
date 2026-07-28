"""Gradio web demo for selfheal.

Shows each generate-run-fix attempt as a collapsible step: the generated
code, its output or error, and (if it failed) the fix that follows.
Deployable as-is to Hugging Face Spaces (``python app.py`` launches it).
"""

from __future__ import annotations

import tempfile
import threading

import gradio as gr

from selfheal import run
from selfheal.config import DEFAULT_MAX_ATTEMPTS, DEFAULT_TIMEOUT_SECONDS, get_api_key
from selfheal.models import Attempt

SAFETY_NOTE = """\
> **Safety note:** the script Claude writes for your task executes on the
> server running this demo, inside a subprocess with a timeout, confined to
> a fresh temporary working directory that's deleted afterward. Don't submit
> tasks you wouldn't want run by an automated script. See the
> [README](https://github.com/sairam400/selfheal#safety) for full details.
"""

EXAMPLE_TASKS = [
    ["Write the first 20 Fibonacci numbers to fib.txt, one per line"],
    ["Count the number of words in all .txt files in the current directory"],
    ["Generate a CSV of 10 fake employees with name, department, and salary columns"],
]

CUSTOM_CSS = """
.gradio-container { max-width: 900px !important; margin: auto !important; }
#title-row { text-align: center; margin-bottom: 0.25em; }
#subtitle { text-align: center; color: var(--body-text-color-subdued); margin-bottom: 1em; }
.status-banner {
    padding: 0.75em 1em; border-radius: 8px; font-weight: 600; margin-top: 1em;
}
.status-success { background: #dcfce7; color: #166534; }
.status-failure { background: #fee2e2; color: #991b1b; }
details.attempt {
    border: 1px solid var(--border-color-primary);
    border-radius: 8px; margin-bottom: 0.75em; padding: 0.5em 0.9em;
}
details.attempt summary { cursor: pointer; font-weight: 600; }
details.attempt-success summary { color: #166534; }
details.attempt-failure summary { color: #991b1b; }
"""


def _attempt_html(attempt: Attempt, attempt_num: int, *, open_by_default: bool) -> str:
    if attempt.succeeded:
        css_class, label = "attempt-success", "SUCCESS"
    elif attempt.timed_out:
        css_class, label = "attempt-failure", "TIMED OUT"
    else:
        css_class, label = "attempt-failure", f"FAILED (exit code {attempt.exit_code})"

    body = [f"```python\n{attempt.code}\n```"]
    if attempt.output:
        body.append(f"**stdout:**\n```\n{attempt.output}\n```")
    if attempt.error:
        body.append(f"**stderr:**\n```\n{attempt.error}\n```")

    open_attr = " open" if open_by_default else ""
    return (
        f'<details class="attempt {css_class}"{open_attr}>'
        f"<summary>Attempt {attempt_num}: {label}</summary>\n\n"
        + "\n\n".join(body)
        + "\n\n</details>"
    )


def _render(sections: list[str], banner: str = "") -> str:
    return banner + "\n\n".join(sections)


def run_task(task: str, max_attempts: int, timeout: int, confirm: bool):
    """Run the selfheal agent loop for the Gradio UI and stream attempt logs.

    Args:
        task: Plain-English task description from the textbox.
        max_attempts: Max generate-run-fix cycles, from the slider.
        timeout: Per-attempt execution timeout in seconds, from the slider.
        confirm: Whether the "I understand" checkbox is ticked.

    Yields:
        Updated HTML/markdown log as each attempt completes.
    """
    if not task.strip():
        yield "Please enter a task above."
        return
    if not confirm:
        yield (
            '<div class="status-banner status-failure">'
            "Please check the confirmation box before running -- generated "
            "code executes on the server. See the safety note above.</div>"
        )
        return

    try:
        get_api_key()
    except RuntimeError as exc:
        yield f'<div class="status-banner status-failure">{exc}</div>'
        return

    sections: list[str] = []
    result_holder: dict = {}

    def on_attempt(attempt: Attempt) -> None:
        sections.append(
            _attempt_html(attempt, len(sections) + 1, open_by_default=not attempt.succeeded)
        )

    def do_run(workdir: str) -> None:
        try:
            result_holder["result"] = run(
                task,
                max_attempts=int(max_attempts),
                timeout=int(timeout),
                workdir=workdir,
                on_attempt=on_attempt,
            )
        except Exception as exc:  # noqa: BLE001 - surface any failure to the UI, not just a crash
            result_holder["exception"] = exc

    with tempfile.TemporaryDirectory(prefix="selfheal_demo_") as workdir:
        thread = threading.Thread(target=do_run, args=(workdir,))
        thread.start()
        last_count = 0
        while thread.is_alive():
            thread.join(timeout=0.5)
            if len(sections) != last_count:
                last_count = len(sections)
                yield _render(sections)
        thread.join()

        if "exception" in result_holder:
            banner = (
                '<div class="status-banner status-failure">'
                f"Error: {result_holder['exception']}</div>\n\n"
            )
            yield _render(sections, banner)
            return

        result = result_holder["result"]
        css_class = "status-success" if result.succeeded else "status-failure"
        label = "Succeeded" if result.succeeded else "Gave up"
        banner = (
            f'<div class="status-banner {css_class}">{label} after '
            f"{result.num_attempts} attempt(s)</div>\n\n"
        )
        yield _render(sections, banner)


with gr.Blocks(title="selfheal") as demo:
    gr.Markdown("# 🩹 selfheal", elem_id="title-row")
    gr.Markdown(
        "Describe a task in plain English. Claude writes a Python script, "
        "runs it, and fixes its own errors until it works or hits the "
        "attempt limit -- every attempt is shown below, in order.",
        elem_id="subtitle",
    )
    gr.Markdown(SAFETY_NOTE)

    task_input = gr.Textbox(
        label="Task",
        placeholder="e.g. count the number of words in all .txt files in the current directory",
        lines=2,
    )
    gr.Examples(examples=EXAMPLE_TASKS, inputs=[task_input], label="Try an example")

    with gr.Accordion("Advanced settings", open=False):
        with gr.Row():
            max_attempts_input = gr.Slider(
                minimum=1, maximum=8, step=1, value=DEFAULT_MAX_ATTEMPTS, label="Max attempts"
            )
            timeout_input = gr.Slider(
                minimum=5,
                maximum=120,
                step=5,
                value=DEFAULT_TIMEOUT_SECONDS,
                label="Timeout (seconds)",
            )

    confirm_input = gr.Checkbox(
        label="I understand this executes generated Python code on the server."
    )
    run_button = gr.Button("Run", variant="primary", size="lg")
    output_html = gr.Markdown()

    run_button.click(
        fn=run_task,
        inputs=[task_input, max_attempts_input, timeout_input, confirm_input],
        outputs=output_html,
    )

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft(primary_hue="orange"), css=CUSTOM_CSS)
