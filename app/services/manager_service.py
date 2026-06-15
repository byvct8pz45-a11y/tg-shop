from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Manager, ManagerRole

logger = logging.getLogger(__name__)


async def get_manager_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[Manager]:
    result = await session.execute(
        select(Manager).where(Manager.telegram_id == telegram_id, Manager.is_active == True)
    )
    return result.scalar_one_or_none()


async def get_all_managers(session: AsyncSession) -> list[Manager]:
    result = await session.execute(
        select(Manager).order_by(Manager.added_at.desc())
    )
    return list(result.scalars().all())


async def add_manager(
    session: AsyncSession,
    telegram_id: int,
    first_name: str,
    username: Optional[str],
    role: ManagerRole,
    added_by: int,
) -> Manager:
    manager = Manager(
        telegram_id=telegram_id,
        first_name=first_name,
        username=username,
        role=role,
        added_by=added_by,
    )
    session.add(manager)
    await session.flush()
    await session.refresh(manager)
    return manager


async def deactivate_manager(session: AsyncSession, telegram_id: int) -> Optional[Manager]:
    manager = await get_manager_by_telegram_id(session, telegram_id)
    if manager is None:
        return None
    manager.is_active = False
    await session.flush()
    return manager


async def is_manager_or_admin(session: AsyncSession, telegram_id: int) -> bool:
    from config import config
    if telegram_id in config.admin_ids:
        return True
    manager = await get_manager_by_telegram_id(session, telegram_id)
    return manager is not None


async def is_admin_role(session: AsyncSession, telegram_id: int) -> bool:
    from config import config
    if telegram_id in config.admin_ids:
        return True
    manager = await get_manager_by_telegram_id(session, telegram_id)
    return manager is not None and manager.role == ManagerRole.ADMIN
