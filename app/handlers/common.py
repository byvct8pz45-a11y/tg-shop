"""Общие команды: /start, /help."""
from __future__ import annotations
import logging
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.keyboards import main_menu_keyboard, admin_main_keyboard
from app.models import User
from app.services import get_welcome_text, get_user_by_telegram_id, is_manager_or_admin
from app.utils import is_admin

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    session: AsyncSession,
    db_user: User,
    command: CommandObject,
) -> None:
    # Реферальная ссылка: /start ref_12345
    if command.args and command.args.startswith("ref_"):
        try:
            ref_tg_id = int(command.args[4:])
            if ref_tg_id != db_user.telegram_id and db_user.referrer_id is None:
                referrer = await get_user_by_telegram_id(session, ref_tg_id)
                if referrer:
                    db_user.referrer_id = referrer.id
                    await session.flush()
                    await message.answer(
                        "🎁 Вы перешли по реферальной ссылке! "
                        "На первый заказ вам начислена скидка 5%."
                    )
        except (ValueError, TypeError):
            pass

    # Администратор сразу видит админ-панель
    user_id = message.from_user.id
    if is_admin(user_id) or await is_manager_or_admin(session, user_id):
        await message.answer(
            "🔧 <b>Панель управления</b>\n\nДобро пожаловать!",
            parse_mode="HTML",
            reply_markup=admin_main_keyboard(),
        )
        return

    welcome = await get_welcome_text(session)
    await message.answer(welcome, reply_markup=main_menu_keyboard(), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(message: Message, session: AsyncSession) -> None:
    user_id = message.from_user.id
    if is_admin(user_id) or await is_manager_or_admin(session, user_id):
        await message.answer(
            "ℹ️ <b>Справка для администратора</b>\n\n"
            "📋 <b>Заказы</b> — управление заказами\n"
            "📊 <b>Статистика</b> — сводные данные\n"
            "⭐ <b>Отзывы</b> — модерация отзывов\n"
            "🎫 <b>Поддержка</b> — обращения клиентов\n"
            "👥 <b>Менеджеры</b> — управление командой\n"
            "💳 <b>Реквизиты</b> — настройка реквизитов",
            parse_mode="HTML",
            reply_markup=admin_main_keyboard(),
        )
        return
    text = (
        "ℹ️ <b>Справка</b>\n\n"
        "📦 <b>Создать заказ</b> — оформить новый заказ\n"
        "📋 <b>Мои заказы</b> — история заказов\n"
        "⭐ <b>Отзывы</b> — отзывы клиентов\n"
        "💬 <b>Поддержка</b> — связаться с менеджером\n"
        "❤️ <b>Избранное</b> — сохранённые товары\n"
        "👤 <b>Профиль</b> — реферальная ссылка, промокоды, бонусы\n\n"
        "Для создания заказа нажмите кнопку ниже 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu_keyboard())


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession) -> None:
    if not (is_admin(message.from_user.id) or await is_manager_or_admin(session, message.from_user.id)):
        await message.answer("🚫 Доступ запрещён.")
        return
    await message.answer("🔧 <b>Панель управления</b>", parse_mode="HTML",
                         reply_markup=admin_main_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message, session: AsyncSession) -> None:
    """Универсальная команда для возврата в меню."""
    user_id = message.from_user.id
    if is_admin(user_id) or await is_manager_or_admin(session, user_id):
        await message.answer("🔧 Панель управления:", reply_markup=admin_main_keyboard())
    else:
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
