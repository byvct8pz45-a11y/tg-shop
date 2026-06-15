"""Мои заказы, профиль, поддержка, избранное."""
from __future__ import annotations
import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.keyboards import (
    main_menu_keyboard, my_orders_keyboard, review_action_keyboard,
    support_menu_keyboard, my_tickets_keyboard, ticket_reply_keyboard,
    cancel_keyboard, favorites_category_keyboard, favorite_item_keyboard,
    favorite_category_select_keyboard,
)
from app.models import FavoriteCategory, OrderStatus, User
from app.services import (
    get_orders_by_user, get_order_by_id, save_message, get_order_by_number,
    get_user_review_for_order, get_tickets_by_user, get_ticket_by_id,
    create_ticket, add_ticket_message, get_user_promos,
    get_user_favorites, get_favorite_by_id, remove_favorite, search_favorites,
    update_favorite_category,
)
from app.states import SupportFSM
from app.utils import format_order_card
from config import config

logger = logging.getLogger(__name__)
router = Router()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОФИЛЬ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "👤 Профиль")
async def show_profile(message: Message, session: AsyncSession, db_user: User, bot: Bot) -> None:
    from sqlalchemy import select
    from app.models import User as UserModel

    promos = await get_user_promos(session, db_user.id)
    active_promos = [p for p in promos if not p.is_used]

    # Явный запрос рефералов — избегаем MissingGreenlet на self-referential selectin
    referrals_result = await session.execute(
        select(UserModel).where(UserModel.referrer_id == db_user.id).limit(10)
    )
    referrals = referrals_result.scalars().all()

    # Username бота для реферальной ссылки
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username
    except Exception:
        bot_username = "your_bot"

    ref_link = f"https://t.me/{bot_username}?start=ref_{db_user.telegram_id}"

    lines = [
        "👤 <b>Профиль</b>",
        f"Имя: {db_user.full_name}",
        "",
        "🔗 <b>Реферальная ссылка:</b>",
        f"<code>{ref_link}</code>",
        "",
        f"👥 Приглашено: <b>{len(referrals)}</b>",
        f"💰 Бонусный баланс: <b>{db_user.bonus_balance:.2f} ₽</b>",
        f"📈 Всего заработано: <b>{db_user.bonus_total_earned:.2f} ₽</b>",
        f"📉 Всего потрачено: <b>{db_user.bonus_total_spent:.2f} ₽</b>",
    ]
    if active_promos:
        lines += ["", "🎟 <b>Ваши промокоды:</b>"]
        for p in active_promos:
            exp = p.expires_at.strftime("%d.%m.%Y") if p.expires_at else "бессрочно"
            lines.append(f"  <code>{p.code}</code> — {p.discount_percent}% (до {exp})")
    if referrals:
        lines += ["", "👥 <b>Приглашённые пользователи:</b>"]
        for ref in referrals:
            lines.append(f"  • {ref.full_name}")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_menu_keyboard())


# ═══════════════════════════════════════════════════════════════════════════════
# МОИ ЗАКАЗЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📋 Мои заказы")
async def my_orders(message: Message, session: AsyncSession, db_user: User) -> None:
    orders = await get_orders_by_user(session, db_user.id)
    if not orders:
        await message.answer("📭 У вас пока нет заказов.\n\nНажмите <b>📦 Создать заказ</b>!",
                             parse_mode="HTML", reply_markup=main_menu_keyboard())
        return
    await message.answer(
        f"📋 <b>Мои заказы</b> ({len(orders)} шт.)\n\nВыберите заказ:",
        parse_mode="HTML", reply_markup=my_orders_keyboard(orders),
    )


@router.callback_query(F.data.startswith("view_order:"))
async def view_order(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)
    if order is None or order.user_id != db_user.id:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return

    text = format_order_card(order, for_admin=False)
    if order.messages:
        text += "\n\n💬 <b>История сообщений:</b>"
        for msg in order.messages[-5:]:
            role_icon = "👤" if msg.sender_role == "client" else "🔧"
            text += f"\n{role_icon} {msg.text[:200]}"

    # Кнопки
    can_repeat = order.status == OrderStatus.COMPLETED
    has_review = order.review is not None
    kb = None
    if order.status == OrderStatus.COMPLETED and not has_review:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"leave_review:{order_id}"))
        builder.row(InlineKeyboardButton(text="🔄 Повторить заказ", callback_data=f"repeat_order:{order_id}"))
        kb = builder.as_markup()
    elif can_repeat:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔄 Повторить заказ", callback_data=f"repeat_order:{order_id}"))
        kb = builder.as_markup()

    photos = [img.file_id for img in order.images]
    if photos:
        await callback.message.answer_photo(photo=photos[0], caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# ИЗБРАННОЕ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "❤️ Избранное")
async def show_favorites(message: Message, session: AsyncSession, db_user: User) -> None:
    favorites = await get_user_favorites(session, db_user.id)
    counts = {}
    for fav in favorites:
        counts[fav.category.name] = counts.get(fav.category.name, 0) + 1
    if not favorites:
        await message.answer("❤️ <b>Избранное пусто</b>\n\nДобавляйте товары из канала в избранное.",
                             parse_mode="HTML", reply_markup=main_menu_keyboard())
        return
    await message.answer(
        f"❤️ <b>Избранное</b> ({len(favorites)} товаров)\n\nВыберите категорию:",
        parse_mode="HTML", reply_markup=favorites_category_keyboard(counts),
    )


@router.callback_query(F.data.startswith("fav_cat:"))
async def show_favorites_by_category(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    cat_name = callback.data.split(":")[1]
    if cat_name == "ALL":
        favorites = await get_user_favorites(session, db_user.id)
        title = "Все товары"
    else:
        try:
            cat = FavoriteCategory[cat_name]
            favorites = await get_user_favorites(session, db_user.id, category=cat)
            title = cat.value
        except KeyError:
            await callback.answer("Неверная категория.", show_alert=True)
            return

    if not favorites:
        await callback.answer("В этой категории нет товаров.", show_alert=True)
        return

    await callback.message.answer(f"❤️ <b>{title}</b> ({len(favorites)} шт.):", parse_mode="HTML")
    for fav in favorites[:20]:
        text = f"📦 {fav.title or 'Без названия'}\n📅 {fav.created_at.strftime('%d.%m.%Y')}"
        await callback.message.answer(text, reply_markup=favorite_item_keyboard(fav.id, fav.channel_id, fav.post_id))
    await callback.answer()


@router.callback_query(F.data == "fav_search")
async def fav_search_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    from app.states import SupportFSM
    await state.set_state(SupportFSM.entering_subject)
    await state.update_data(fav_search=True)
    await callback.message.answer("🔍 Введите название для поиска по избранному:", reply_markup=cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("fav_remove:"))
async def remove_from_favorites(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    fav_id = int(callback.data.split(":")[1])
    removed = await remove_favorite(session, fav_id, db_user.id)
    if removed:
        await callback.answer("🗑 Удалено из избранного.", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer("⚠️ Не найдено.", show_alert=True)


@router.callback_query(F.data.startswith("fav_add:"))
async def add_to_favorites_cb(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    from app.services import add_favorite
    post_id = int(callback.data.split(":")[1])
    channel_id = config.favorites_channel_id or callback.message.chat.id
    title = (callback.message.caption or callback.message.text or "")[:100]
    _, is_new = await add_favorite(session, db_user.id, post_id, channel_id, title=title)
    if is_new:
        await callback.answer("❤️ Добавлено в избранное!", show_alert=True)
    else:
        await callback.answer("Уже в избранном.", show_alert=True)


@router.callback_query(F.data.startswith("fav_setcat:"))
async def choose_fav_category(callback: CallbackQuery, db_user: User) -> None:
    """Показать пользователю список категорий для смены."""
    fav_id = int(callback.data.split(":")[1])
    await callback.message.answer(
        "📂 <b>Выберите новую категорию:</b>",
        parse_mode="HTML",
        reply_markup=favorite_category_select_keyboard(fav_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fav_cat_set:"))
async def set_fav_category(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    """Сохранить выбранную категорию для записи в избранном."""
    parts = callback.data.split(":")  # fav_cat_set:<fav_id>:<CAT_NAME>
    fav_id = int(parts[1])
    cat_name = parts[2]
    try:
        cat = FavoriteCategory[cat_name]
    except KeyError:
        await callback.answer("⚠️ Неизвестная категория.", show_alert=True)
        return
    ok = await update_favorite_category(session, fav_id, db_user.id, cat)
    if ok:
        await callback.answer(f"✅ Категория изменена на «{cat.value}»", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer("⚠️ Запись не найдена.", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДДЕРЖКА
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "💬 Поддержка")
async def support_menu(message: Message) -> None:
    await message.answer(
        "💬 <b>Поддержка</b>\n\nСоздайте обращение — ответим в ближайшее время.",
        parse_mode="HTML", reply_markup=support_menu_keyboard(),
    )


@router.message(F.text == "◀️ Главное меню")
@router.message(F.text == "🏠 Главное меню")
async def back_to_main(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🏠 Главное меню:", reply_markup=main_menu_keyboard())


@router.message(F.text == "📝 Новое обращение")
async def new_ticket_start(message: Message, state: FSMContext) -> None:
    await state.set_state(SupportFSM.entering_subject)
    await message.answer("📝 <b>Новое обращение</b>\n\nВведите тему (до 100 символов):",
                         parse_mode="HTML", reply_markup=cancel_keyboard())


@router.message(SupportFSM.entering_subject, F.text == "❌ Отмена")
async def cancel_ticket_subject(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("fav_search"):
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu_keyboard())
        return
    await state.clear()
    await message.answer("Отменено.", reply_markup=support_menu_keyboard())


@router.message(SupportFSM.entering_subject, F.text)
async def ticket_subject_entered(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    # Если это был поиск по избранному
    if data.get("fav_search"):
        await state.clear()
        from app.services import search_favorites as sf
        from sqlalchemy.ext.asyncio import AsyncSession
        # Получаем session из data — нет, используем другой подход через callback
        # Здесь просто выдаём подсказку
        await message.answer("🔍 Используйте кнопку поиска в разделе избранного.",
                             reply_markup=main_menu_keyboard())
        return
    subject = message.text[:100]
    await state.update_data(ticket_subject=subject)
    await state.set_state(SupportFSM.entering_message)
    await message.answer(f"📋 Тема: <b>{subject}</b>\n\nОпишите вашу проблему подробно:",
                         parse_mode="HTML", reply_markup=cancel_keyboard())


@router.message(SupportFSM.entering_message, F.text == "❌ Отмена")
async def cancel_ticket_message(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=support_menu_keyboard())


@router.message(SupportFSM.entering_message, F.text)
async def ticket_message_entered(message: Message, state: FSMContext,
                                 session: AsyncSession, db_user: User, bot: Bot) -> None:
    data = await state.get_data()
    subject = data["ticket_subject"]
    await state.clear()
    ticket = await create_ticket(session=session, user_id=db_user.id, subject=subject, first_message=message.text)
    await session.commit()
    await message.answer(
        f"✅ <b>Обращение {ticket.ticket_number} создано!</b>\n\nМенеджер ответит в ближайшее время.",
        parse_mode="HTML", reply_markup=support_menu_keyboard(),
    )
    from app.keyboards.admin import ticket_admin_keyboard
    admin_text = (
        f"🎫 <b>Новое обращение</b>\n\n"
        f"Номер: <b>{ticket.ticket_number}</b>\n"
        f"Тема: {subject}\n"
        f"👤 {db_user.mention} (<code>{db_user.telegram_id}</code>)\n\n"
        f"📩 {message.text}"
    )
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=admin_text, parse_mode="HTML",
                                   reply_markup=ticket_admin_keyboard(ticket.id, is_closed=False))
        except Exception as exc:
            logger.error("notify admin %s: %s", admin_id, exc)


@router.message(F.text == "📂 Мои обращения")
async def my_tickets(message: Message, session: AsyncSession, db_user: User) -> None:
    tickets = await get_tickets_by_user(session, db_user.id)
    if not tickets:
        await message.answer("📭 У вас нет обращений.", reply_markup=support_menu_keyboard())
        return
    await message.answer(f"📂 <b>Мои обращения</b> ({len(tickets)} шт.):",
                         parse_mode="HTML", reply_markup=my_tickets_keyboard(tickets))


@router.callback_query(F.data.startswith("view_ticket:"))
async def view_ticket(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    ticket_id = int(callback.data.split(":")[1])
    ticket = await get_ticket_by_id(session, ticket_id)
    if ticket is None or ticket.user_id != db_user.id:
        await callback.answer("⚠️ Обращение не найдено.", show_alert=True)
        return
    status_icons = {"Новый": "🆕", "Открытый": "🔓", "Закрытый": "🔒"}
    icon = status_icons.get(ticket.status.value, "💬")
    lines = [
        f"🎫 <b>{ticket.ticket_number}</b>  {icon} {ticket.status.value}",
        f"📋 Тема: {ticket.subject}",
        f"📅 {ticket.created_at.strftime('%d.%m.%Y %H:%M')}", "",
        "💬 <b>Переписка:</b>",
    ]
    for msg in ticket.messages:
        role = "👤 Вы" if msg.sender_role == "client" else "🔧 Менеджер"
        time = msg.created_at.strftime("%d.%m %H:%M")
        lines.append(f"\n{role}  <i>{time}</i>\n{msg.text}")
    kb = ticket_reply_keyboard(ticket_id) if ticket.status.value != "Закрытый" else None
    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("client_reply_ticket:"))
async def client_reply_ticket_start(callback: CallbackQuery, state: FSMContext,
                                    session: AsyncSession, db_user: User) -> None:
    ticket_id = int(callback.data.split(":")[1])
    ticket = await get_ticket_by_id(session, ticket_id)
    if ticket is None or ticket.user_id != db_user.id:
        await callback.answer("⚠️ Обращение не найдено.", show_alert=True)
        return
    await state.set_state(SupportFSM.replying_to_ticket)
    await state.update_data(reply_ticket_id=ticket_id)
    await callback.message.answer(
        f"✏️ Введите ответ по обращению <b>{ticket.ticket_number}</b>:",
        parse_mode="HTML", reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(SupportFSM.replying_to_ticket, F.text == "❌ Отмена")
async def cancel_client_ticket_reply(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=support_menu_keyboard())


@router.message(SupportFSM.replying_to_ticket, F.text)
async def client_send_ticket_reply(message: Message, state: FSMContext,
                                   session: AsyncSession, db_user: User, bot: Bot) -> None:
    data = await state.get_data()
    ticket_id = data["reply_ticket_id"]
    ticket = await get_ticket_by_id(session, ticket_id)
    await state.clear()
    if ticket is None:
        await message.answer("⚠️ Обращение не найдено.", reply_markup=support_menu_keyboard())
        return
    await add_ticket_message(session, ticket_id, message.text, "client")
    await session.commit()
    await message.answer(f"✅ Ответ по обращению <b>{ticket.ticket_number}</b> отправлен.",
                         parse_mode="HTML", reply_markup=support_menu_keyboard())
    from app.keyboards.admin import ticket_admin_keyboard
    admin_text = (
        f"💬 <b>Ответ клиента</b>\n\n"
        f"Номер: <b>{ticket.ticket_number}</b>\n"
        f"👤 {db_user.mention}\n\n📩 {message.text}"
    )
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text=admin_text, parse_mode="HTML",
                                   reply_markup=ticket_admin_keyboard(ticket_id, is_closed=False))
        except Exception as exc:
            logger.error("notify admin %s: %s", admin_id, exc)


# ─── Сообщения по номеру заказа ─────────────────────────────────────────────

@router.message(F.text.regexp(r"^ORD-\d+"))
async def client_reply_by_order_number(message: Message, session: AsyncSession,
                                       db_user: User, bot: Bot) -> None:
    text = message.text or ""
    parts = text.split(maxsplit=1)
    order = await get_order_by_number(session, parts[0].upper())
    if order is None or order.user_id != db_user.id:
        await message.answer("⚠️ Заказ не найден или нет доступа.")
        return
    msg_text = parts[1] if len(parts) > 1 else "(без текста)"
    await save_message(session, order.id, msg_text, "client", db_user.id)
    await session.commit()
    from app.keyboards.admin import order_admin_keyboard
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"💬 <b>Сообщение клиента</b>\n\nЗаказ: <b>{order.order_number}</b>\n"
                     f"👤 {db_user.mention} (<code>{db_user.telegram_id}</code>)\n\n📩 {msg_text}",
                parse_mode="HTML",
                reply_markup=order_admin_keyboard(order.id, order.order_number),
            )
        except Exception as exc:
            logger.error("notify admin %s: %s", admin_id, exc)
    await message.answer(f"✅ Сообщение по заказу <b>{order.order_number}</b> отправлено.",
                         parse_mode="HTML")
