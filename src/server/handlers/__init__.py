# SPDX-License-Identifier: MIT

from fastapi import APIRouter

from src.server.handlers.scheduler import router as scheduler_router

router = APIRouter()
router.include_router(scheduler_router)