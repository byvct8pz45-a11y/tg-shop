from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Favorite, FavoriteCategory

logger = logging.getLogger(__name__)


async def add_favorite(
    session: AsyncSession,
    user_id: int,
    post_id: int,
    channel_id: int,
    title: Optional[str] = None,
    category: FavoriteCategory = FavoriteCategory.OTHER,
) -> tuple[Favorite, bool]:
    """Добавить в избранное. Возвращает (favorite, is_new)."""
    result = await session.execute(
        select(Favorite).where(
            and_(Favorite.user_id == user_id, Favorite.post_id == post_id, Favorite.channel_id == channel_id)
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing, False
    fav = Favorite(
        user_id=user_id,
        post_id=post_id,
        channel_id=channel_id,
        title=title,
        category=category,
    )
    session.add(fav)
    await session.flush()
    return fav, True


async def remove_favorite(session: AsyncSession, favorite_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(Favorite).where(Favorite.id == favorite_id, Favorite.user_id == user_id)
    )
    fav = result.scalar_one_or_none()
    if fav is None:
        return False
    await session.delete(fav)
    await session.flush()
    return True


async def get_user_favorites(
    session: AsyncSession,
    user_id: int,
    category: Optional[FavoriteCategory] = None,
) -> list[Favorite]:
    q = select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.created_at.desc())
    if category is not None:
        q = q.where(Favorite.category == category)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_favorite_by_id(session: AsyncSession, favorite_id: int) -> Optional[Favorite]:
    result = await session.execute(select(Favorite).where(Favorite.id == favorite_id))
    return result.scalar_one_or_none()


async def search_favorites(session: AsyncSession, user_id: int, query: str) -> list[Favorite]:
    result = await session.execute(
        select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.title.ilike(f"%{query}%"),
        ).order_by(Favorite.created_at.desc())
    )
    return list(result.scalars().all())
