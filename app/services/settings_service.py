from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting

DEFAULT_WELCOME = (
    "👋 <b>Добро пожаловать!</b>\n\n"
    "Мы поможем вам заказать товары из Китая.\n\n"
    "Выберите действие:"
)

DEFAULT_PAYMENT_DETAILS = (
    "💳 <b>Реквизиты для оплаты</b>\n\n"
    "Карта: <code>0000 0000 0000 0000</code>\n"
    "Получатель: Иван И.\n\n"
    "⚠️ После оплаты отправьте скриншот менеджеру."
)


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def set_setting(session: AsyncSession, key: str, value: str) -> Setting:
    result = await session.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = Setting(key=key, value=value)
        session.add(setting)
    else:
        setting.value = value
    await session.flush()
    return setting


async def get_welcome_text(session: AsyncSession) -> str:
    return await get_setting(session, "welcome_text", DEFAULT_WELCOME)


async def get_payment_details(session: AsyncSession) -> str:
    return await get_setting(session, "payment_details", DEFAULT_PAYMENT_DETAILS)
