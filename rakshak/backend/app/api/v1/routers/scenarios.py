"""
Scenarios router (/api/v1/scenarios).
Executes simulated test scenarios (S1-S4) to evaluate multi-modal corroboration.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_current_user, require_permission
from app.models.user import User
from app.scenario_runner import ScenarioRunner

router = APIRouter(prefix="/scenarios", tags=["Scenarios"])


@router.get("", response_model=List[Dict[str, Any]], dependencies=[Depends(require_permission("scenarios:run"))])
async def list_scenarios(current_user: User = Depends(get_current_user)):
    """List all available pre-scripted multi-modal scenarios."""
    return ScenarioRunner.list_scenarios()


@router.post("/{scenario_id}/play", dependencies=[Depends(require_permission("scenarios:run"))])
async def play_scenario(
    scenario_id: str,
    speed: float = Query(1.0, ge=0.01, le=200.0, description="Simulation speed multiplier (e.g. 50.0 for tests)"),
    current_user: User = Depends(get_current_user),
):
    """
    Play scenario for current organization.
    Runs mock/real detectors and access engine concurrently against real Fusion Engine.
    """
    scenario_data = ScenarioRunner.load_scenario(scenario_id)
    result = await ScenarioRunner.run_scenario(
        org_id=current_user.org_id,
        scenario_data=scenario_data,
        speed=speed,
    )
    return result


@router.post("/stop", dependencies=[Depends(require_permission("scenarios:run"))])
async def stop_scenario(current_user: User = Depends(get_current_user)):
    """Stop currently active simulation for this organization."""
    ScenarioRunner.stop_scenario(current_user.org_id)
    return {"message": "Simulation stopped."}


@router.post("/reset", dependencies=[Depends(require_permission("scenarios:run"))])
async def reset_scenario(current_user: User = Depends(get_current_user)):
    """
    Reset organization signals, incidents, and access events.
    PRESERVES the tamper-evident audit log for compliance.
    """
    result = await ScenarioRunner.reset_scenario(
        org_id=current_user.org_id,
        actor_email=current_user.email,
    )
    return result
