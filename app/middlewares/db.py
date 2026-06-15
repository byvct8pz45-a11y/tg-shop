from __future__ import annotations
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from app.database import AsyncSessionLocal
from app.services import get_or_create_user


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        async with AsyncSessionLocal() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        from_user = data.get("event_from_user")
        session = data.get("session")
        # channel_post не имеет from_user — пропускаем создание db_user
        if from_user and session:
            referrer_id = data.get("_referrer_id")
            db_user = await get_or_create_user(session, from_user, referrer_id=referrer_id)
            data["db_user"] = db_user
        return await handler(event, data)
