from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Review, ReviewStatus, User

logger = logging.getLogger(__name__)


async def create_review(
    session: AsyncSession,
    user: User,
    order_id: int,
    rating: int,
    text: str,
    photo_file_id: Optional[str] = None,
) -> Review:
    review = Review(
        user_id=user.id,
        order_id=order_id,
        telegram_id=user.telegram_id,
        username=user.username,
        rating=rating,
        text=text,
        photo_file_id=photo_file_id,
        status=ReviewStatus.PENDING,
    )
    session.add(review)
    await session.flush()
    await session.refresh(review)
    return review


async def get_review_by_id(session: AsyncSession, review_id: int) -> Optional[Review]:
    result = await session.execute(
        select(Review).where(Review.id == review_id).options(selectinload(Review.user))
    )
    return result.scalar_one_or_none()


async def get_published_reviews(session: AsyncSession, limit: int = 10) -> list[Review]:
    result = await session.execute(
        select(Review)
        .where(Review.status == ReviewStatus.APPROVED)
        .order_by(Review.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_all_reviews(session: AsyncSession, limit: int = 30) -> list[Review]:
    result = await session.execute(
        select(Review)
        .options(selectinload(Review.user))
        .order_by(Review.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_pending_reviews(session: AsyncSession) -> list[Review]:
    result = await session.execute(
        select(Review)
        .where(Review.status == ReviewStatus.PENDING)
        .options(selectinload(Review.user))
        .order_by(Review.created_at.asc())
    )
    return list(result.scalars().all())


async def get_user_review_for_order(
    session: AsyncSession, user_id: int, order_id: int
) -> Optional[Review]:
    result = await session.execute(
        select(Review).where(Review.user_id == user_id, Review.order_id == order_id)
    )
    return result.scalar_one_or_none()


async def approve_review(session: AsyncSession, review_id: int) -> Optional[Review]:
    review = await get_review_by_id(session, review_id)
    if review is None:
        return None
    review.status = ReviewStatus.APPROVED
    await session.flush()
    return review


async def reject_review(session: AsyncSession, review_id: int) -> Optional[Review]:
    review = await get_review_by_id(session, review_id)
    if review is None:
        return None
    review.status = ReviewStatus.REJECTED
    await session.flush()
    return review


async def delete_review(session: AsyncSession, review_id: int) -> bool:
    review = await get_review_by_id(session, review_id)
    if review is None:
        return False
    await session.delete(review)
    await session.flush()
    return True
