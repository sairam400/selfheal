"""Anthropic API wrapper: prompt construction and code extraction.

Keeps all Claude-specific request/response handling in one place so the
agent loop in :mod:`selfheal.agent` stays focused on control flow.
"""

from __future__ import annotations

import re

import anthropic

from .config import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, get_api_key

SYSTEM_PROMPT = """\
You are selfheal, an expert Python coding agent. Given a plain-English task, \
you write a single self-contained Python script that accomplishes it.

Rules:
- Output ONLY a single Python code block (```python ... ```). No prose \
before or after it.
- The script must be self-contained and runnable as-is with `python script.py`.
- Only use the Python standard library unless the task clearly requires a \
well-known third-party package, in which case assume it is installed.
- Print human-readable progress and results to stdout.
- Write defensively: check that files/paths exist before operating on them, \
and raise clear errors instead of failing silently.
- The script runs with its working directory as the task's target directory; \
use relative paths unless the task specifies otherwise.
"""

FIX_PROMPT_TEMPLATE = """\
The following Python script was generated for this task:

TASK: {task}

```python
{code}
```

Running it failed with this error:

```
{error}
```

Write a corrected, complete, self-contained version of the script that \
fixes this error. Output ONLY a single Python code block with the full \
corrected script -- do not include explanations or diffs.
"""

_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(response_text: str) -> str:
    """Pull the Python source out of Claude's markdown-fenced response.

    Args:
        response_text: The raw text content of Claude's reply.

    Returns:
        The code inside the first ```python fenced block, or the raw text
        stripped of whitespace if no fenced block is found (defensive
        fallback in case Claude omits the fence).
    """
    match = _CODE_BLOCK_RE.search(response_text)
    if match:
        return match.group(1).strip()
    return response_text.strip()


class ClaudeClient:
    """Thin wrapper around the Anthropic SDK for the selfheal agent loop."""

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        """Create a client bound to a specific Claude model.

        Args:
            model: The Claude model id to use for all requests.
            max_tokens: Maximum tokens to request in each completion.
        """
        self._client = anthropic.Anthropic(api_key=get_api_key())
        self.model = model
        self.max_tokens = max_tokens

    def generate_script(self, task: str) -> str:
        """Ask Claude to write a first-draft script for a task.

        Args:
            task: Plain-English description of what the script should do.

        Returns:
            The extracted Python source code.
        """
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"TASK: {task}"}],
        )
        return extract_code(response.content[0].text)

    def fix_script(self, task: str, code: str, error: str) -> str:
        """Ask Claude to fix a script given the traceback it produced.

        Args:
            task: The original plain-English task.
            code: The script that failed.
            error: The captured stderr/traceback from running ``code``.

        Returns:
            The extracted, corrected Python source code.
        """
        prompt = FIX_PROMPT_TEMPLATE.format(task=task, code=code, error=error)
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return extract_code(response.content[0].text)
