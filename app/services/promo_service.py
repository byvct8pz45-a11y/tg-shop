from __future__ import annotations

import logging
import random
import string
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Order, Promo, User

logger = logging.getLogger(__name__)

FIRST_ORDER_PROMO_DISCOUNT = 5.0
PROMO_DAYS_VALID = 90


def _generate_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


async def generate_unique_code(session: AsyncSession) -> str:
    for _ in range(10):
        code = _generate_code()
        exists = await session.execute(select(Promo).where(Promo.code == code))
        if exists.scalar_one_or_none() is None:
            return code
    return _generate_code(12)


# ─── Автопромокод за первый заказ (привязан к пользователю) ─────────────────

async def issue_first_order_promo(session: AsyncSession, user: User) -> Optional[Promo]:
    """Выдать персональный промокод за первый заказ."""
    if user.first_order_promo_issued:
        return None
    code = await generate_unique_code(session)
    promo = Promo(
        code=code,
        discount_type="percent",
        discount_percent=FIRST_ORDER_PROMO_DISCOUNT,
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=PROMO_DAYS_VALID),
    )
    session.add(promo)
    user.first_order_promo_issued = True
    await session.flush()
    logger.info("Promo %s issued to user %s", code, user.telegram_id)
    return promo


# ─── Глобальные промокоды от администратора ─────────────────────────────────

async def create_admin_promo(
    session: AsyncSession,
    code: str,
    discount_type: str,  # "percent" | "fixed"
    discount_value: float,
    created_by: int,
    expires_days: Optional[int] = None,
) -> tuple[Optional[Promo], str]:
    """Создать глобальный промокод. Возвращает (promo, error)."""
    code = code.upper().strip()
    if not code:
        return None, "Код не может быть пустым."
    existing = await session.execute(select(Promo).where(Promo.code == code))
    if existing.scalar_one_or_none():
        return None, f"Промокод <code>{code}</code> уже существует."
    if discount_type not in ("percent", "fixed"):
        return None, "Неверный тип скидки."
    if discount_value <= 0:
        return None, "Скидка должна быть больше 0."
    if discount_type == "percent" and discount_value > 100:
        return None, "Процент скидки не может превышать 100."
    expires_at = datetime.utcnow() + timedelta(days=expires_days) if expires_days else None
    promo = Promo(
        code=code,
        discount_type=discount_type,
        discount_percent=discount_value if discount_type == "percent" else 0.0,
        discount_fixed=discount_value if discount_type == "fixed" else 0.0,
        user_id=None,  # глобальный
        created_by=created_by,
        expires_at=expires_at,
    )
    session.add(promo)
    await session.flush()
    logger.info("Admin promo %s created by %s", code, created_by)
    return promo, ""


async def get_promo_by_code(session: AsyncSession, code: str) -> Optional[Promo]:
    result = await session.execute(select(Promo).where(Promo.code == code.upper().strip()))
    return result.scalar_one_or_none()


async def validate_promo_for_order(
    session: AsyncSession,
    code: str,
    user_id: int,
    order_total: Optional[float] = None,
) -> tuple[Optional[Promo], str]:
    """
    Валидация промокода при применении к заказу.
    Возвращает (promo, error_msg). Если error_msg пустой — промокод валиден.
    """
    promo = await get_promo_by_code(session, code)
    if promo is None:
        return None, "❌ Промокод не найден."
    if promo.is_used:
        return None, "❌ Промокод уже был использован."
    if promo.expires_at and promo.expires_at < datetime.utcnow():
        return None, "❌ Срок действия промокода истёк."
    # Если промокод персональный — проверяем принадлежность
    if promo.user_id is not None and promo.user_id != user_id:
        return None, "❌ Этот промокод вам не принадлежит."
    return promo, ""


# Оставляем старое имя как алиас для обратной совместимости
async def validate_promo(
    session: AsyncSession, code: str, user_id: int
) -> tuple[Optional[Promo], str]:
    return await validate_promo_for_order(session, code, user_id)


def calculate_promo_discount(promo: Promo, base_amount: float) -> float:
    """Рассчитать сумму скидки по промокоду."""
    if promo.discount_type == "percent":
        return round(base_amount * promo.discount_percent / 100, 2)
    elif promo.discount_type == "fixed":
        return min(promo.discount_fixed, base_amount)
    return 0.0


async def use_promo(
    session: AsyncSession, promo: Promo, order_id: int, user_id: Optional[int] = None
) -> None:
    promo.is_used = True
    promo.used_in_order_id = order_id
    promo.used_by_user_id = user_id
    promo.usage_count += 1
    await session.flush()


async def delete_promo(session: AsyncSession, promo_id: int) -> bool:
    result = await session.execute(select(Promo).where(Promo.id == promo_id))
    promo = result.scalar_one_or_none()
    if promo is None:
        return False
    await session.delete(promo)
    await session.flush()
    return True


async def get_all_promos(session: AsyncSession) -> list[Promo]:
    result = await session.execute(
        select(Promo).order_by(Promo.created_at.desc())
    )
    return list(result.scalars().all())


async def get_user_promos(session: AsyncSession, user_id: int) -> list[Promo]:
    """Персональные промокоды пользователя (выданные за первый заказ)."""
    result = await session.execute(
        select(Promo).where(Promo.user_id == user_id).order_by(Promo.created_at.desc())
    )
    return list(result.scalars().all())
