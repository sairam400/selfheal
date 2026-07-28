# Contributing to selfheal

Thanks for your interest in improving selfheal! This is a small project and
contributions of all sizes are welcome — bug fixes, docs, tests, new
examples.

## Setup

```bash
git clone https://github.com/sairam400/selfheal.git
cd selfheal
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev,web]"
cp .env.example .env  # then add your ANTHROPIC_API_KEY
```

## Running tests

Tests mock all Anthropic API calls and subprocess execution, so they run
offline and don't need an API key:

```bash
pytest
```

## Linting

```bash
ruff check .
```

CI runs both `ruff check` and `pytest` on every push and pull request.

## Making changes

1. Open an issue first for anything beyond a small fix, so we can discuss
   the approach before you invest time.
2. Keep pull requests focused — one logical change per PR.
3. Add or update tests for any behavior change.
4. Make sure `ruff check .` and `pytest` both pass locally before opening
   a PR.
5. Write clear commit messages explaining *why*, not just *what*.

## Code style

- Type hints on public functions, docstrings on all public functions and
  classes.
- Prefer clarity over cleverness — this codebase is meant to be easy to
  read end-to-end.
- No `exec`/`eval` of generated code, ever — it must run in the sandboxed
  subprocess in `selfheal/executor.py`.

## Reporting security issues

If you find a way for generated code to escape the sandbox, or another
security-relevant issue, please open an issue describing it (this project
has no dedicated security contact yet, so a public issue is fine for now,
but feel free to redact exploit details).
