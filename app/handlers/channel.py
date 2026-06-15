"""Обработчик постов из Telegram-канала: добавление кнопки «В избранное»."""
from __future__ import annotations
import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message

from app.keyboards.client import add_to_favorite_keyboard
from config import config

logger = logging.getLogger(__name__)

# Роутер для channel_post обновлений
router = Router()


@router.channel_post(F.photo | F.text | F.video | F.document | F.animation)
async def handle_channel_post(message: Message, bot: Bot) -> None:
    """Добавляем кнопку «❤️ В избранное» к каждому посту в канале."""
    if config.favorites_channel_id and message.chat.id != config.favorites_channel_id:
        return  # Реагируем только на наш канал

    post_id = message.message_id
    kb = add_to_favorite_keyboard(post_id)

    try:
        # Если у поста уже есть reply_markup — добавляем нашу кнопку
        current_kb = message.reply_markup
        if current_kb:
            # Просто добавляем кнопку к существующей клавиатуре
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            builder = InlineKeyboardBuilder.from_markup(current_kb)
            builder.row(InlineKeyboardButton(
                text="❤️ Добавить в избранное",
                callback_data=f"fav_add:{post_id}",
            ))
            kb = builder.as_markup()

        await bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=post_id,
            reply_markup=kb,
        )
    except Exception as exc:
        logger.debug("Could not edit channel post markup: %s", exc)
