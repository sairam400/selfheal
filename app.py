"""Gradio web demo for selfheal.

Shows each generate-run-fix attempt as a collapsible step: the generated
code, its output or error, and (if it failed) the fix that follows, with an
explicit "healing" connector between a failure and the attempt that fixes
it. Deployable as-is to Hugging Face Spaces (``python app.py`` launches it).
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

# The first example references an input file that won't exist in the demo's
# empty scratch directory, so attempt 1 reliably fails with a real
# FileNotFoundError and attempt 2 has to actually fix it -- genuine
# self-healing, not staged.
EXAMPLE_TASKS = [
    [
        "Read sales_data.csv (columns: product, quantity, price) and print "
        "the total revenue, then save a one-line summary to revenue_summary.txt"
    ],
    ["Read employees.csv and write employees_over_30.csv with only rows where age > 30"],
    ["Write the first 20 Fibonacci numbers to fib.txt, one per line"],
]

CUSTOM_CSS = """
.gradio-container { max-width: 900px !important; margin: auto !important; }

#hero {
    text-align: center;
    padding: 1.75em 1em 1.4em;
    border-radius: 16px;
    margin-bottom: 1em;
    background: linear-gradient(135deg, #fb923c 0%, #f97316 50%, #ea580c 100%);
}
#hero h1 { color: white; font-size: 2.1em; margin: 0 0 0.25em; }
#hero p { color: rgba(255,255,255,0.94); margin: 0; font-size: 1.02em; line-height: 1.5; }

.status-banner {
    padding: 0.9em 1.2em; border-radius: 10px; font-weight: 700; margin-top: 1em;
    font-size: 1.05em; animation: fadeIn 0.4s ease-out;
}
.status-success { background: #dcfce7; color: #166534; border: 1px solid #86efac; }
.status-failure { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }

@media (prefers-color-scheme: dark) {
    .status-success { background: #052e1a; color: #4ade80; border-color: #166534; }
    .status-failure { background: #2c0b0b; color: #f87171; border-color: #991b1b; }
}

details.attempt {
    border-radius: 10px; margin-bottom: 0.9em; padding: 0.7em 1em 0.8em;
    background: var(--background-fill-secondary);
    border-left: 5px solid var(--border-color-primary);
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    animation: fadeIn 0.4s ease-out;
}
details.attempt summary { cursor: pointer; font-weight: 700; font-size: 1.02em; list-style: none; }
details.attempt summary::-webkit-details-marker { display: none; }
details.attempt summary::before { content: "\\25B8  "; }
details.attempt[open] summary::before { content: "\\25BE  "; }
details.attempt-success { border-left-color: #22c55e; }
details.attempt-failure { border-left-color: #ef4444; }
details.attempt-success summary { color: #16a34a; }
details.attempt-failure summary { color: #dc2626; }

.healing-connector {
    text-align: center; margin: -0.4em 0 1em; font-weight: 600;
    color: #ea580c; font-size: 0.95em; animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
}
"""

HEALING_CONNECTOR = (
    '<div class="healing-connector">'
    "\U0001f527 <strong>Self-healing:</strong> Claude reads the traceback above "
    "and rewrites the script &darr;</div>"
)


def _attempt_html(attempt: Attempt, attempt_num: int) -> str:
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

    return (
        f'<details class="attempt {css_class}" open>'
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
        Updated HTML/markdown log as each attempt completes. A visible
        "self-healing" connector is inserted immediately after any failed
        attempt (while Claude is generating the fix) so the loop's purpose
        -- read the error, rewrite the code -- is explicit, not implied.
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
    attempt_count = [0]
    result_holder: dict = {}

    def on_attempt(attempt: Attempt) -> None:
        attempt_count[0] += 1
        sections.append(_attempt_html(attempt, attempt_count[0]))
        if not attempt.succeeded and attempt_count[0] < int(max_attempts):
            sections.append(HEALING_CONNECTOR)

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
        icon = "✅" if result.succeeded else "❌"
        label = "Succeeded" if result.succeeded else "Gave up"
        banner = (
            f'<div class="status-banner {css_class}">{icon} {label} after '
            f"{result.num_attempts} attempt(s)</div>\n\n"
        )
        yield _render(sections, banner)


with gr.Blocks(title="selfheal") as demo:
    gr.HTML(
        '<div id="hero"><h1>\U0001fa79 selfheal</h1>'
        "<p>Describe a task in plain English. Claude writes a Python script and runs it.<br>"
        "If it errors, Claude reads the traceback and rewrites the code &mdash; "
        "watch that healing loop happen live below.</p></div>"
    )
    gr.Markdown(SAFETY_NOTE)

    task_input = gr.Textbox(
        label="Task",
        placeholder="e.g. count the number of words in all .txt files in the current directory",
        lines=2,
    )
    gr.Examples(
        examples=EXAMPLE_TASKS,
        inputs=[task_input],
        label="Try an example (the first is designed to fail once, then heal itself)",
    )

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
