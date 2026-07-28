"""selfheal: a coding agent that writes, runs, and fixes its own scripts.

Public API:

    from selfheal import run

    result = run("rename all .jpg files in ./photos by the date they were taken")
    # result.succeeded, result.final_code, result.attempts, result.result_output
"""

from .agent import run
from .models import Attempt, RunResult

__all__ = ["run", "Attempt", "RunResult"]

__version__ = "0.1.0"
