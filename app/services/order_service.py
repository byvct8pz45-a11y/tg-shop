from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Order, OrderImage, OrderStatus, Message

logger = logging.getLogger(__name__)


async def _generate_order_number(session: AsyncSession) -> str:
    result = await session.execute(select(func.count()).select_from(Order))
    count = result.scalar_one() or 0
    return f"ORD-{(count + 1):06d}"


async def create_order(
    session: AsyncSession,
    user_id: int,
    description: str,
    photo_file_ids: list[str],
    found_price: Optional[str] = None,
    desired_budget: Optional[str] = None,
    source_order_id: Optional[int] = None,
    promo_code: Optional[str] = None,
    discount_amount: float = 0.0,
    bonus_used: float = 0.0,
) -> Order:
    order_number = await _generate_order_number(session)
    order = Order(
        order_number=order_number,
        user_id=user_id,
        description=description,
        found_price=found_price,
        desired_budget=desired_budget,
        source_order_id=source_order_id,
        promo_code=promo_code,
        discount_amount=discount_amount,
        bonus_used=bonus_used,
    )
    session.add(order)
    await session.flush()

    for fid in photo_file_ids:
        session.add(OrderImage(order_id=order.id, file_id=fid))
    await session.flush()
    await session.refresh(order)
    return order


async def get_order_by_id(session: AsyncSession, order_id: int) -> Optional[Order]:
    result = await session.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.user),
            selectinload(Order.images),
            selectinload(Order.messages),
            selectinload(Order.review),
            selectinload(Order.manager),
        )
    )
    return result.scalar_one_or_none()


async def get_order_by_number(session: AsyncSession, order_number: str) -> Optional[Order]:
    result = await session.execute(
        select(Order)
        .where(Order.order_number == order_number)
        .options(
            selectinload(Order.user),
            selectinload(Order.images),
            selectinload(Order.messages),
            selectinload(Order.review),
            selectinload(Order.manager),
        )
    )
    return result.scalar_one_or_none()


async def get_orders_by_user(session: AsyncSession, user_id: int) -> list[Order]:
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .options(selectinload(Order.images), selectinload(Order.review))
        .order_by(Order.created_at.desc())
    )
    return list(result.scalars().all())


async def get_recent_orders(
    session: AsyncSession,
    limit: int = 10,
    manager_id: Optional[int] = None,
    status: Optional[OrderStatus] = None,
) -> list[Order]:
    q = (
        select(Order)
        .options(selectinload(Order.user), selectinload(Order.images), selectinload(Order.manager))
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    if manager_id is not None:
        q = q.where(Order.manager_id == manager_id)
    if status is not None:
        q = q.where(Order.status == status)
    result = await session.execute(q)
    return list(result.scalars().all())


async def update_order_status(
    session: AsyncSession,
    order_id: int,
    new_status: OrderStatus,
) -> Optional[Order]:
    order = await get_order_by_id(session, order_id)
    if order is None:
        return None
    order.status = new_status
    if new_status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
        from datetime import datetime
        order.closed_at = datetime.utcnow()
    await session.flush()
    return order


async def set_order_pricing(
    session: AsyncSession,
    order_id: int,
    item_price: float,
    delivery_price: float,
    commission: float,
) -> Optional[Order]:
    order = await get_order_by_id(session, order_id)
    if order is None:
        return None
    order.item_price = item_price
    order.delivery_price = delivery_price
    order.commission = commission
    order.total_price = item_price + delivery_price + commission - order.discount_amount - order.bonus_used
    order.status = OrderStatus.AWAITING_APPROVAL
    await session.flush()
    return order


async def set_order_cancel_reason(
    session: AsyncSession,
    order_id: int,
    reason: str,
) -> Optional[Order]:
    order = await get_order_by_id(session, order_id)
    if order is None:
        return None
    order.cancel_reason = reason
    order.status = OrderStatus.CANCELLED
    await session.flush()
    return order


async def assign_manager(
    session: AsyncSession,
    order_id: int,
    manager_id: int,
) -> Optional[Order]:
    order = await get_order_by_id(session, order_id)
    if order is None:
        return None
    order.manager_id = manager_id
    await session.flush()
    return order


async def save_message(
    session: AsyncSession,
    order_id: int,
    text: str,
    sender_role: str,
    user_id: Optional[int] = None,
) -> Message:
    msg = Message(order_id=order_id, text=text, sender_role=sender_role, user_id=user_id)
    session.add(msg)
    await session.flush()
    return msg


async def get_stats(session: AsyncSession) -> dict:
    total = (await session.execute(select(func.count()).select_from(Order))).scalar_one()
    new = (await session.execute(select(func.count()).select_from(Order).where(Order.status == OrderStatus.NEW))).scalar_one()
    active_statuses = [
        OrderStatus.CALCULATING, OrderStatus.AWAITING_APPROVAL,
        OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID,
        OrderStatus.PURCHASED, OrderStatus.IN_TRANSIT, OrderStatus.RECEIVED,
    ]
    in_progress = (
        await session.execute(
            select(func.count()).select_from(Order).where(Order.status.in_(active_statuses))
        )
    ).scalar_one()
    completed = (await session.execute(select(func.count()).select_from(Order).where(Order.status == OrderStatus.COMPLETED))).scalar_one()
    cancelled = (await session.execute(select(func.count()).select_from(Order).where(Order.status == OrderStatus.CANCELLED))).scalar_one()

    from app.models import User
    users_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()

    # Сумма комиссий
    commission_sum_result = await session.execute(
        select(func.sum(Order.commission)).where(Order.commission.isnot(None))
    )
    commission_sum = commission_sum_result.scalar_one() or 0.0

    return {
        "total": total,
        "new": new,
        "in_progress": in_progress,
        "completed": completed,
        "cancelled": cancelled,
        "users": users_count,
        "commission_sum": commission_sum,
    }
