"""TBG06 scenario."""

from __future__ import annotations

from app.evaluation.full_function.actions import EvalContext
from app.evaluation.full_function.scenario_handlers import HANDLERS
from app.evaluation.full_function.scenarios._common import ScenarioRunResult


def run(ctx: EvalContext) -> ScenarioRunResult:
    return HANDLERS["TBG06"](ctx)
