"""HTTP routers extracted from the historical god-file `main.py`.

Phase D keeps behavior identical; create_app() includes these routers and only
owns wiring / leftover endpoints that have not been moved yet.
"""

from app.api.assets import create_assets_router
from app.api.actions import create_actions_router
from app.api.candidates import create_candidates_router
from app.api.directions import create_directions_router
from app.api.four_stage import create_four_stage_router
from app.api.realtime_observation import create_realtime_observation_router
from app.api.generation import create_generation_router
from app.api.perception import create_perception_router
from app.api.sandbox import create_sandbox_router
from app.api.sessions import create_sessions_router
from app.api.system import create_system_router
from app.api.projects import create_projects_router
from app.api.interaction import create_interaction_router

__all__ = [
    "create_assets_router",
    "create_actions_router",
    "create_candidates_router",
    "create_directions_router",
    "create_four_stage_router",
    "create_realtime_observation_router",
    "create_generation_router",
    "create_perception_router",
    "create_sandbox_router",
    "create_sessions_router",
    "create_system_router",
    "create_projects_router",
    "create_interaction_router",
]
