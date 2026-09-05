"""HTTP routing only; business decisions live in modules."""

from fastapi import APIRouter

from accord_api.api.health import router as health_router
from accord_api.api.state_api import router as state_router
from accord_api.modules.activity.api import router as activity_router
from accord_api.modules.agent_runs.api import router as runs_router
from accord_api.modules.collaboration.api import router as collaboration_router
from accord_api.modules.collaboration.groups_api import router as groups_router
from accord_api.modules.coordination.api import router as coordination_router
from accord_api.modules.identity.api import router as identity_router
from accord_api.modules.knowledge.api import router as resources_router
from accord_api.modules.preferences.api import router as preferences_router
from accord_api.modules.topics.api import router as topics_router
from accord_api.modules.tutorial.api import router as tutorial_router
from accord_api.modules.workspace.api import router as workspace_router

router = APIRouter()
router.include_router(coordination_router)
router.include_router(identity_router)
router.include_router(workspace_router)
router.include_router(topics_router)
router.include_router(activity_router)
router.include_router(preferences_router)
router.include_router(groups_router)
router.include_router(collaboration_router)
router.include_router(runs_router)
router.include_router(resources_router)
router.include_router(tutorial_router)
router.include_router(state_router)
router.include_router(health_router)
