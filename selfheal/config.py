"""Configuration and constants for selfheal.

Centralizes the Claude model id, default runtime limits, and environment
loading so the rest of the codebase never hardcodes these values.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load variables from a .env file in the current working directory (if present).
# This is a no-op if no .env file exists, so it's safe to call unconditionally.
load_dotenv()

# Single source of truth for which Claude model selfheal talks to.
# Swap this constant to change the model everywhere in the codebase.
DEFAULT_MODEL = "claude-sonnet-4-5"

# Agent loop defaults.
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_TOKENS = 4096

ANTHROPIC_API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"


def get_api_key() -> str:
    """Read the Anthropic API key from the environment.

    Returns:
        The API key string.

    Raises:
        RuntimeError: If ``ANTHROPIC_API_KEY`` is not set. The message points
            the user at ``.env.example`` rather than failing silently.
    """
    api_key = os.environ.get(ANTHROPIC_API_KEY_ENV_VAR)
    if not api_key:
        raise RuntimeError(
            f"{ANTHROPIC_API_KEY_ENV_VAR} is not set. Copy .env.example to .env "
            "and add your key, or export it in your shell."
        )
    return api_key
