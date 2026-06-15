from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BonusOperationType, BonusTransaction, User

logger = logging.getLogger(__name__)

REFERRAL_DISCOUNT_PERCENT = 5.0   # скидка приглашённому на первый заказ
REFERRAL_REWARD_PERCENT = 5.0     # вознаграждение рефереру от комиссии


async def add_bonus(
    session: AsyncSession,
    user: User,
    amount: float,
    operation_type: BonusOperationType,
    order_id: Optional[int] = None,
    description: Optional[str] = None,
) -> None:
    if amount <= 0:
        return
    user.bonus_balance += amount
    user.bonus_total_earned += amount
    tx = BonusTransaction(
        user_id=user.id,
        operation_type=operation_type,
        amount=amount,
        order_id=order_id,
        description=description,
    )
    session.add(tx)
    await session.flush()
    logger.info("Bonus +%.2f to user %s (%s)", amount, user.telegram_id, operation_type.value)


async def spend_bonus(
    session: AsyncSession,
    user: User,
    amount: float,
    order_id: Optional[int] = None,
) -> float:
    """Списать бонусы. Возвращает фактически списанную сумму."""
    actual = min(amount, user.bonus_balance)
    if actual <= 0:
        return 0.0
    user.bonus_balance -= actual
    user.bonus_total_spent += actual
    tx = BonusTransaction(
        user_id=user.id,
        operation_type=BonusOperationType.BONUS_USED,
        amount=-actual,
        order_id=order_id,
        description="Использование бонусного баланса",
    )
    session.add(tx)
    await session.flush()
    logger.info("Bonus -%.2f from user %s", actual, user.telegram_id)
    return actual


async def process_referral_reward(
    session: AsyncSession,
    invited_user: User,
    commission: float,
    order_id: int,
) -> None:
    """Начислить реферальное вознаграждение рефереру после первой оплаты."""
    if invited_user.referrer_id is None:
        return
    result = await session.execute(select(User).where(User.id == invited_user.referrer_id))
    referrer = result.scalar_one_or_none()
    if referrer is None:
        return
    reward = round(commission * REFERRAL_REWARD_PERCENT / 100, 2)
    await add_bonus(
        session, referrer, reward,
        BonusOperationType.REFERRAL_REWARD,
        order_id=order_id,
        description=f"Реферальное вознаграждение за заказ {order_id}",
    )
    logger.info("Referral reward %.2f to referrer %s", reward, referrer.telegram_id)
