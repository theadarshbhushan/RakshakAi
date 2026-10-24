"""
Evaluation router (/api/v1/eval).
Returns multi-modal model precision, recall, and detection latency benchmark metrics.
"""
import json
from typing import Dict, Any
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/eval", tags=["Evaluation"])


@router.get("/results", response_model=Dict[str, Any])
async def get_eval_results():
    """Retrieve evaluation metrics from data/eval/results.json if present, else empty structure."""
    results_file = settings.EVAL_DIR / "results.json"
    if results_file.exists():
        try:
            with open(results_file, "r", encoding="utf-8") as rf:
                return json.load(rf)
        except Exception:
            pass
    return {}
