"""
Evaluation router (/api/v1/eval).
Serves multi-modal model precision, recall, and detection latency benchmark metrics.
Enables owner/admin to trigger background re-evaluation runs.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends

from app.core.config import settings
from app.core.deps import get_current_user, require_permission
from app.models.user import User

logger = logging.getLogger("rakshakai.eval")

router = APIRouter(prefix="/eval", tags=["Evaluation"])


async def _run_eval_background():
    """Background task executing ml/eval/run_eval.py."""
    try:
        from ml.eval.run_eval import run_evaluation
        await run_evaluation()
    except Exception as e:
        logger.error(f"Error running background evaluation: {e}", exc_info=e)


@router.get("/results", response_model=Dict[str, Any])
async def get_eval_results():
    """Retrieve evaluation metrics from ml/eval/results/results.json if present, else empty structure."""
    candidate_paths = [
        settings.EVAL_RESULTS_DIR / "results.json",
        settings.PROJECT_ROOT / "ml" / "eval" / "results" / "results.json",
        settings.EVAL_DIR / "results.json",
        settings.PROJECT_ROOT / "data" / "eval" / "results.json",
        Path("ml/eval/results/results.json").resolve(),
        Path("data/eval/results.json").resolve(),
        Path("../ml/eval/results/results.json").resolve(),
        Path("../data/eval/results.json").resolve(),
    ]
    for path in candidate_paths:
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as rf:
                    data = json.load(rf)
                    if data:
                        return data
            except Exception as e:
                logger.warning(f"Failed to read evaluation results from {path}: {e}")
    return {}


@router.post("/run", dependencies=[Depends(require_permission("rules:write"))])
async def trigger_eval_run(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """
    Trigger full offline evaluation suite in background (owner/admin only).
    Updates data/eval/results.json and generation charts.
    """
    background_tasks.add_task(_run_eval_background)
    return {
        "status": "started",
        "message": "Evaluation suite started in background.",
        "triggered_by": current_user.email,
    }
