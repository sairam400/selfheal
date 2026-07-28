"""Command-line interface for selfheal.

Streams each generate-run-fix cycle to the terminal with rich formatting:
the generated code, its output, any error in red, and a clear success/
failure marker.
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from .agent import run as run_agent
from .config import DEFAULT_MAX_ATTEMPTS, DEFAULT_MODEL, DEFAULT_TIMEOUT_SECONDS
from .llm import ClaudeClient
from .models import Attempt

console = Console()


def _print_code(code: str, attempt_num: int) -> None:
    syntax = Syntax(code, "python", theme="monokai", line_numbers=True, word_wrap=True)
    title = f"[bold cyan]Attempt {attempt_num}: generated code[/]"
    console.print(Panel(syntax, title=title, border_style="cyan"))


def _print_attempt_result(attempt: Attempt, attempt_num: int) -> None:
    if attempt.succeeded:
        console.print(
            Panel(
                attempt.output or "[dim](no stdout)[/]",
                title=f"[bold green]Attempt {attempt_num}: output[/]",
                border_style="green",
            )
        )
        console.print(f"[bold green]:heavy_check_mark: Success on attempt {attempt_num}![/]")
    else:
        label = "timed out" if attempt.timed_out else f"exit code {attempt.exit_code}"
        console.print(
            Panel(
                attempt.error or "[dim](no stderr)[/]",
                title=f"[bold red]Attempt {attempt_num}: error ({label})[/]",
                border_style="red",
            )
        )


def _make_on_attempt(state: dict) -> callable:
    def on_attempt(attempt: Attempt) -> None:
        state["count"] += 1
        _print_code(attempt.code, state["count"])
        _print_attempt_result(attempt, state["count"])
        if not attempt.succeeded:
            console.print("[yellow]Asking Claude to fix the error...[/]")

    return on_attempt


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the ``selfheal`` command."""
    parser = argparse.ArgumentParser(
        prog="selfheal",
        description="A coding agent that writes, runs, and fixes its own Python scripts.",
    )
    parser.add_argument("task", help="Plain-English description of the task to accomplish")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print the script without executing it",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm you want to execute the generated code on this machine",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=f"Maximum generate-run-fix cycles (default: {DEFAULT_MAX_ATTEMPTS})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Seconds per run before it's killed (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--workdir",
        default=".",
        help="Directory the generated script executes in (default: current directory)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Claude model id to use (default: {DEFAULT_MODEL})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``selfheal`` console script.

    Args:
        argv: Argument list to parse; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: 0 on success, 1 on failure or missing confirmation.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    console.print(Panel(f"[bold]{args.task}[/]", title="selfheal task", border_style="magenta"))

    if args.dry_run:
        console.print("[yellow]--dry-run: generating script only, nothing will be executed.[/]")
        client = ClaudeClient(model=args.model)
        code = client.generate_script(args.task)
        _print_code(code, 1)
        console.print("[dim]Re-run without --dry-run (and with --yes) to execute this script.[/]")
        return 0

    if not args.yes:
        console.print(
            "[bold red]Refusing to execute generated code without confirmation.[/]\n"
            "Generated code runs directly on your machine and can read, write, "
            "or delete files. Review it first, then re-run with [bold]--yes[/] "
            "to proceed, or use [bold]--dry-run[/] to just see the code."
        )
        return 1

    state = {"count": 0}
    result = run_agent(
        args.task,
        max_attempts=args.max_attempts,
        timeout=args.timeout,
        workdir=args.workdir,
        model=args.model,
        on_attempt=_make_on_attempt(state),
    )

    if result.succeeded:
        console.print(
            Panel(
                f"[bold green]Task completed in {result.num_attempts} attempt(s).[/]",
                border_style="green",
            )
        )
        return 0

    console.print(
        Panel(
            f"[bold red]Gave up after {result.num_attempts} attempt(s). "
            "See the last error above.[/]",
            border_style="red",
        )
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
