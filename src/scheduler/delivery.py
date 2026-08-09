"""Delivery — record results in job_runs, optionally push to social channel.

Per spec §11.6: db write always succeeds first; social push is best-effort
and its failure does NOT downgrade the job's overall status.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from src.scheduler.types import DeliveryMode, ScheduledJob
from src.social.channels import ReplyTarget

logger = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    delivered: bool
    channel: Optional[str] = None
    error: Optional[str] = None


class JobDelivery:
    def __init__(self, *, store, social_router=None):
        """`social_router` is either a router or a zero-arg callable returning
        one. Delivery is built during engine startup, before social adapters
        exist, so the callable form defers resolution to send time."""
        self._store = store
        self._router = social_router

    def _resolve_router(self):
        if callable(self._router):
            try:
                return self._router()
            except Exception as e:
                logger.warning(f"social router resolution failed: {e}")
                return None
        return self._router

    async def deliver(
        self,
        run_id: int,
        job: ScheduledJob,
        result_text: str,
    ) -> DeliveryResult:
        preview = (result_text or "")[:2000]
        if job.delivery_mode == DeliveryMode.DB_ONLY:
            try:
                self._store.update_run(run_id, delivery_status="ok")
            except Exception as e:
                logger.warning(f"run {run_id} delivery_status update failed: {e}")
            return DeliveryResult(delivered=True, channel="db")

        if job.delivery_mode == DeliveryMode.SOCIAL:
            if not preview.strip():
                self._store.update_run(
                    run_id, delivery_status="failed",
                    delivery_error="empty result, nothing to send",
                )
                return DeliveryResult(delivered=False, error="empty result")
            target = job.delivery_target
            if not target:
                self._store.update_run(
                    run_id, delivery_status="failed",
                    delivery_error="missing delivery_target",
                )
                return DeliveryResult(delivered=False, error="missing target")
            return await self._push_social(run_id, job, preview, target)

        return DeliveryResult(delivered=False, error=f"unknown delivery_mode: {job.delivery_mode}")

    async def _push_social(
        self,
        run_id: int,
        job: ScheduledJob,
        text: str,
        target: str,
    ) -> DeliveryResult:
        router = self._resolve_router()
        if router is None:
            self._store.update_run(
                run_id, delivery_status="failed",
                delivery_error="no social router configured",
            )
            return DeliveryResult(delivered=False, error="no router")

        platform, kind, dest_id = _parse_target(target)
        if not platform:
            self._store.update_run(
                run_id, delivery_status="failed",
                delivery_error=f"invalid target format: {target}",
            )
            return DeliveryResult(delivered=False, error="invalid target")

        adapter = router.get(platform)
        if adapter is None:
            self._store.update_run(
                run_id, delivery_status="failed",
                delivery_error=f"platform not enabled: {platform}",
            )
            return DeliveryResult(delivered=False, error="platform disabled")

        if dest_id is None:
            # Bare platform name → bot owner's default DM (wechat).
            dest_id = adapter.default_peer()
            if not dest_id:
                self._store.update_run(
                    run_id, delivery_status="failed",
                    delivery_error=f"no default peer for {platform}",
                )
                return DeliveryResult(delivered=False, error="no default peer")

        reply = ReplyTarget(platform=platform, peer_id=dest_id)
        try:
            # ChannelAdapter.send returns None and raises on failure.
            await asyncio.wait_for(adapter.send(reply, text), timeout=30)
            self._store.update_run(run_id, delivery_status="ok")
            return DeliveryResult(delivered=True, channel=platform)
        except asyncio.TimeoutError:
            self._store.update_run(
                run_id, delivery_status="failed",
                delivery_error="adapter timeout",
            )
            return DeliveryResult(delivered=False, error="timeout")
        except Exception as e:
            self._store.update_run(
                run_id, delivery_status="failed",
                delivery_error=str(e)[:500],
            )
            return DeliveryResult(delivered=False, error=str(e)[:500])


def _parse_target(target: str) -> tuple[str | None, str | None, str | None]:
    """Parse '<platform>:<kind>:<id>' → (platform, kind, id).

    Bare 'wechat' is accepted with kind/id None; the delivery path resolves
    them to the bot owner's default DM via the adapter's default_peer().
    """
    if target == "wechat":
        return "wechat", None, None
    parts = target.split(":", 2)
    if len(parts) != 3:
        return None, None, None
    platform, kind, dest_id = parts
    if platform not in ("feishu", "telegram", "wechat"):
        return None, None, None
    if kind not in ("user", "chat", "group"):
        return None, None, None
    if not dest_id:
        return None, None, None
    return platform, kind, dest_id