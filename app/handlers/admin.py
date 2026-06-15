"""Административная панель."""
from __future__ import annotations
import logging
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.keyboards import (
    admin_main_keyboard, cancel_admin_keyboard, order_admin_keyboard,
    review_admin_keyboard, status_change_keyboard, support_filter_keyboard,
    ticket_admin_keyboard, pricing_confirm_keyboard, orders_filter_keyboard,
    manager_action_keyboard,
)
from app.keyboards.client import ticket_reply_keyboard, pricing_response_keyboard
from app.models import ManagerRole, OrderStatus, ReviewStatus, TicketStatus, User
from app.services import (
    get_order_by_id, get_order_by_number, get_recent_orders, get_stats,
    get_welcome_text, save_message, set_setting, get_payment_details,
    update_order_status, set_order_pricing,
    get_all_reviews, approve_review, reject_review, delete_review,
    get_pending_reviews, get_review_by_id,
    get_all_tickets, get_ticket_by_id, add_ticket_message, close_ticket, reopen_ticket,
    get_all_managers, add_manager, deactivate_manager, is_admin_role,
    issue_first_order_promo, get_user_promos, get_all_users,
    process_referral_reward,
)
from app.states import AdminFSM
from app.utils import format_order_card, format_pricing_card, is_admin, notify_client_status_change, STATUS_EMOJI
from config import config

logger = logging.getLogger(__name__)
router = Router()


def _check_access(user_id: int) -> bool:
    return is_admin(user_id)


async def _check_manager_access(user_id: int, session: AsyncSession) -> bool:
    from app.services import is_manager_or_admin
    return await is_manager_or_admin(session, user_id)


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНОЕ МЕНЮ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📊 Статистика")
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    if not await _check_manager_access(message.from_user.id, session):
        return
    stats = await get_stats(session)
    await message.answer(
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{stats['users']}</b>\n"
        f"📦 Всего заказов: <b>{stats['total']}</b>\n"
        f"🆕 Новые: <b>{stats['new']}</b>\n"
        f"⚙️ Активные: <b>{stats['in_progress']}</b>\n"
        f"🎉 Завершённые: <b>{stats['completed']}</b>\n"
        f"❌ Отменённые: <b>{stats['cancelled']}</b>\n"
        f"💰 Сумма комиссий: <b>{stats['commission_sum']:.2f} ₽</b>",
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАКАЗЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📋 Заказы")
async def admin_orders_menu(message: Message, session: AsyncSession) -> None:
    if not await _check_manager_access(message.from_user.id, session):
        return
    await message.answer("📋 Выберите фильтр заказов:", reply_markup=orders_filter_keyboard())


@router.callback_query(F.data.startswith("orders_filter:"))
async def admin_orders_filtered(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    f = callback.data.split(":")[1]
    active_statuses = [
        OrderStatus.CALCULATING, OrderStatus.AWAITING_APPROVAL,
        OrderStatus.AWAITING_PAYMENT, OrderStatus.PAID,
        OrderStatus.PURCHASED, OrderStatus.IN_TRANSIT, OrderStatus.RECEIVED,
    ]
    if f == "NEW":
        orders = await get_recent_orders(session, limit=20, status=OrderStatus.NEW)
    elif f == "ACTIVE":
        from sqlalchemy import select
        from app.models import Order
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(Order).where(Order.status.in_(active_statuses))
            .options(selectinload(Order.user))
            .order_by(Order.created_at.desc()).limit(20)
        )
        orders = list(result.scalars().all())
    elif f == "COMPLETED":
        orders = await get_recent_orders(session, limit=20, status=OrderStatus.COMPLETED)
    else:
        orders = await get_recent_orders(session, limit=20)

    if not orders:
        await callback.answer("Заказов не найдено.", show_alert=True)
        return

    lines = [f"📋 <b>Заказы</b> ({len(orders)} шт.)\n"]
    for order in orders:
        emoji = STATUS_EMOJI.get(order.status, "📦")
        lines.append(
            f"{emoji} <b>{order.order_number}</b> — {order.status.value}\n"
            f"   👤 {order.user.mention}  📅 {order.created_at.strftime('%d.%m %H:%M')}"
        )
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


@router.message(F.text == "🔍 Найти заказ")
async def find_order_prompt(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_manager_access(message.from_user.id, session):
        return
    await state.set_state(AdminFSM.entering_order_number)
    await message.answer("Введите номер заказа (например: <code>ORD-000001</code>):",
                         parse_mode="HTML", reply_markup=cancel_admin_keyboard())


@router.message(AdminFSM.entering_order_number, F.text)
async def find_order_by_input(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    order = await get_order_by_number(session, message.text.strip().upper())
    await state.clear()
    if order is None:
        await message.answer("⚠️ Заказ не найден.", reply_markup=admin_main_keyboard())
        return
    await _send_order_card_to_admin(message, order)


# ─── Inline: статус заказа ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_open:"))
async def admin_open_order(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    order = await get_order_by_id(session, int(callback.data.split(":")[1]))
    if order is None:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return
    await _send_order_card_to_admin(callback.message, order)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_status:"))
async def admin_change_status_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    order = await get_order_by_id(session, int(callback.data.split(":")[1]))
    if order is None:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return
    await callback.message.answer(
        f"📝 Выберите новый статус для <b>{order.order_number}</b>:",
        parse_mode="HTML", reply_markup=status_change_keyboard(order.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_status:"))
async def admin_set_status(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("⚠️ Неверный формат.", show_alert=True)
        return
    _, order_id_str, status_name = parts
    try:
        new_status = OrderStatus[status_name]
    except KeyError:
        await callback.answer("⚠️ Неверный статус.", show_alert=True)
        return
    order = await update_order_status(session, int(order_id_str), new_status)
    if order is None:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return

    # Если завершён — выдаём промокод за первый заказ и реферальное вознаграждение
    if new_status == OrderStatus.COMPLETED:
        promo = await issue_first_order_promo(session, order.user)
        if promo:
            try:
                await bot.send_message(
                    chat_id=order.user.telegram_id,
                    text=f"🎉 <b>Поздравляем с завершением заказа!</b>\n\n"
                         f"За первый заказ вы получили промокод на скидку {promo.discount_percent}%:\n"
                         f"<code>{promo.code}</code>\n\n"
                         f"Срок действия: {promo.expires_at.strftime('%d.%m.%Y')}",
                    parse_mode="HTML",
                )
            except Exception as exc:
                logger.error("send promo error: %s", exc)

        # Реферальное вознаграждение
        if order.commission:
            await process_referral_reward(session, order.user, order.commission, order.id)

        # Просим оставить отзыв
        from app.keyboards.client import review_action_keyboard
        try:
            await bot.send_message(
                chat_id=order.user.telegram_id,
                text=f"✅ <b>Ваш заказ {order.order_number} успешно завершён!</b>\n\n"
                     "Оцените качество нашего обслуживания:",
                parse_mode="HTML",
                reply_markup=review_action_keyboard(order.id),
            )
        except Exception as exc:
            logger.error("send review prompt error: %s", exc)

    await session.commit()
    await notify_client_status_change(bot, order)
    await callback.answer(f"✅ Статус: «{new_status.value}»", show_alert=True)


@router.callback_query(F.data.startswith("admin_close:"))
async def admin_close_order(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    order = await update_order_status(session, int(callback.data.split(":")[1]), OrderStatus.CANCELLED)
    if order is None:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return
    await session.commit()
    await notify_client_status_change(bot, order)
    await callback.answer(f"🔒 Заказ {order.order_number} отменён.", show_alert=True)


# ─── Расчёт стоимости ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_calc:"))
async def admin_calc_start(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    order_id = int(callback.data.split(":")[1])
    await state.set_state(AdminFSM.entering_item_price)
    await state.update_data(calc_order_id=order_id)
    await callback.message.answer("🧮 <b>Расчёт стоимости</b>\n\nВведите стоимость товара (в рублях):",
                                  parse_mode="HTML", reply_markup=cancel_admin_keyboard())
    await callback.answer()


@router.message(AdminFSM.entering_item_price, F.text)
async def admin_calc_item_price(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    try:
        price = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("⚠️ Введите число, например: <code>2500</code>", parse_mode="HTML")
        return
    await state.update_data(item_price=price)
    await state.set_state(AdminFSM.entering_delivery_price)
    await message.answer("📦 Введите стоимость доставки (в рублях):", reply_markup=cancel_admin_keyboard())


@router.message(AdminFSM.entering_delivery_price, F.text)
async def admin_calc_delivery(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    try:
        delivery = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("⚠️ Введите число.", reply_markup=cancel_admin_keyboard())
        return
    data = await state.get_data()
    item_price = data["item_price"]
    commission = round((item_price + delivery) * 0.15, 2)
    await state.update_data(delivery_price=delivery, auto_commission=commission)
    await state.set_state(AdminFSM.editing_commission)
    order = await get_order_by_id(session, data["calc_order_id"])
    discount = order.discount_amount if order else 0.0
    bonus = order.bonus_used if order else 0.0
    total = round(item_price + delivery + commission - discount - bonus, 2)
    await state.update_data(calculated_total=total)
    await message.answer(
        f"🧮 <b>Предварительный расчёт</b>\n\n"
        f"Товар: <b>{item_price:.2f} ₽</b>\n"
        f"Доставка: <b>{delivery:.2f} ₽</b>\n"
        f"Комиссия (15%): <b>{commission:.2f} ₽</b>\n"
        f"Скидка: <b>-{discount:.2f} ₽</b>\n"
        f"Итого: <b>{total:.2f} ₽</b>\n\n"
        "Введите новую сумму комиссии или нажмите <b>Оставить</b>:",
        parse_mode="HTML",
        reply_markup=cancel_admin_keyboard(),
    )


@router.message(AdminFSM.editing_commission, F.text)
async def admin_calc_commission(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    data = await state.get_data()
    if message.text.lower() in ("оставить", "ок", "ok", "+"):
        commission = data["auto_commission"]
    else:
        try:
            commission = float(message.text.replace(",", ".").replace(" ", ""))
        except ValueError:
            await message.answer("⚠️ Введите число или напишите «оставить».", reply_markup=cancel_admin_keyboard())
            return

    order_id = data["calc_order_id"]
    order = await set_order_pricing(session, order_id, data["item_price"], data["delivery_price"], commission)
    await state.clear()
    if order is None:
        await message.answer("⚠️ Заказ не найден.", reply_markup=admin_main_keyboard())
        return
    await session.commit()

    await message.answer(
        f"✅ Расчёт сохранён для <b>{order.order_number}</b>.\n\n"
        + format_pricing_card(order),
        parse_mode="HTML",
        reply_markup=pricing_confirm_keyboard(order.id),
    )


@router.callback_query(F.data.startswith("edit_commission:"))
async def admin_edit_commission(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)
    if order is None:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return
    await state.set_state(AdminFSM.editing_commission)
    await state.update_data(
        calc_order_id=order_id,
        item_price=order.item_price,
        delivery_price=order.delivery_price,
        auto_commission=order.commission,
    )
    await callback.message.answer(
        f"✏️ Текущая комиссия: <b>{order.commission:.2f} ₽</b>\n\nВведите новую сумму:",
        parse_mode="HTML", reply_markup=cancel_admin_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("send_pricing:"))
async def admin_send_pricing(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    order = await get_order_by_id(session, int(callback.data.split(":")[1]))
    if order is None:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return
    try:
        await bot.send_message(
            chat_id=order.user.telegram_id,
            text=format_pricing_card(order),
            parse_mode="HTML",
            reply_markup=pricing_response_keyboard(order.id),
        )
        await callback.answer("✅ Расчёт отправлен клиенту.", show_alert=True)
    except Exception as exc:
        logger.error("send pricing error: %s", exc)
        await callback.answer("⚠️ Не удалось отправить.", show_alert=True)


# ─── Ответ клиенту по заказу ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_reply:"))
async def admin_reply_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not _check_access(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    order_id = int(callback.data.split(":")[1])
    await state.set_state(AdminFSM.replying_to_client)
    await state.update_data(reply_order_id=order_id)
    await callback.message.answer("✏️ Введите сообщение для клиента:", reply_markup=cancel_admin_keyboard())
    await callback.answer()


@router.message(AdminFSM.replying_to_client, F.text)
async def admin_send_reply(message: Message, state: FSMContext,
                           session: AsyncSession, bot: Bot) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    data = await state.get_data()
    order = await get_order_by_id(session, data["reply_order_id"])
    if order is None:
        await state.clear()
        await message.answer("⚠️ Заказ не найден.", reply_markup=admin_main_keyboard())
        return
    await save_message(session, order.id, message.text, "admin")
    await session.commit()
    try:
        await bot.send_message(
            chat_id=order.user.telegram_id,
            text=f"📩 <b>Сообщение от менеджера</b>\n\n"
                 f"📦 Заказ: <b>{order.order_number}</b>\n\n💬 {message.text}",
            parse_mode="HTML",
        )
        await state.clear()
        await message.answer("✅ Сообщение отправлено.", reply_markup=admin_main_keyboard())
    except Exception as exc:
        logger.error("send reply error: %s", exc)
        await state.clear()
        await message.answer("⚠️ Не удалось доставить (бот заблокирован?).", reply_markup=admin_main_keyboard())


# ═══════════════════════════════════════════════════════════════════════════════
# НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "✏️ Приветствие")
async def cmd_set_welcome(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _check_access(message.from_user.id):
        return
    current = await get_welcome_text(session)
    await state.set_state(AdminFSM.setting_welcome)
    await message.answer(f"✏️ <b>Текущее приветствие:</b>\n\n{current}\n\nВведите новый текст:",
                         parse_mode="HTML", reply_markup=cancel_admin_keyboard())


@router.message(AdminFSM.setting_welcome, F.text)
async def save_welcome(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    await set_setting(session, "welcome_text", message.text)
    await state.clear()
    await message.answer("✅ Приветствие обновлено!", reply_markup=admin_main_keyboard())


@router.message(F.text == "💳 Реквизиты")
async def cmd_set_payment(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not _check_access(message.from_user.id):
        return
    current = await get_payment_details(session)
    await state.set_state(AdminFSM.setting_payment_details)
    await message.answer(f"💳 <b>Текущие реквизиты:</b>\n\n{current}\n\nВведите новые реквизиты:",
                         parse_mode="HTML", reply_markup=cancel_admin_keyboard())


@router.message(AdminFSM.setting_payment_details, F.text)
async def save_payment_details(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    await set_setting(session, "payment_details", message.text)
    await state.clear()
    await message.answer("✅ Реквизиты обновлены!", reply_markup=admin_main_keyboard())


# ═══════════════════════════════════════════════════════════════════════════════
# ОТЗЫВЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "⭐ Отзывы")
async def admin_reviews_list(message: Message, session: AsyncSession) -> None:
    if not await _check_manager_access(message.from_user.id, session):
        return
    pending = await get_pending_reviews(session)
    all_reviews = await get_all_reviews(session, limit=10)
    if pending:
        await message.answer(f"⭐ <b>Отзывы на модерации</b> ({len(pending)} шт.):", parse_mode="HTML")
        for rv in pending:
            stars = "⭐" * rv.rating
            text = f"👤 {rv.user.mention}\nОценка: {stars}\n\n{rv.text}"
            if rv.photo_file_id:
                await message.answer_photo(photo=rv.photo_file_id, caption=text,
                                           reply_markup=review_admin_keyboard(rv.id, "PENDING"))
            else:
                await message.answer(text, reply_markup=review_admin_keyboard(rv.id, "PENDING"))
    if not all_reviews:
        await message.answer("Отзывов пока нет.")
        return
    lines = [f"\n📋 <b>Все отзывы</b> ({len(all_reviews)} шт.):\n"]
    for rv in all_reviews:
        status_icon = {"PENDING": "⏳", "APPROVED": "✅", "REJECTED": "❌"}.get(rv.status.name, "?")
        lines.append(f"{status_icon} {'⭐'*rv.rating} {rv.user.mention} — {rv.created_at.strftime('%d.%m.%Y')}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data.startswith("review_approve:"))
async def admin_approve_review(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    review_id = int(callback.data.split(":")[1])
    review = await approve_review(session, review_id)
    if review is None:
        await callback.answer("⚠️ Отзыв не найден.", show_alert=True)
        return
    await session.commit()
    await callback.answer("✅ Отзыв одобрен.", show_alert=True)
    # Уведомить пользователя
    try:
        await bot.send_message(
            chat_id=review.telegram_id,
            text="✅ <b>Ваш отзыв одобрен</b> и теперь виден другим пользователям!",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("notify user review approved: %s", exc)
    # Публикация в канал отзывов
    if config.reviews_channel_id:
        try:
            stars = "⭐" * review.rating
            text = f"{stars} {review.user.mention}\n\n{review.text}"
            if review.photo_file_id:
                await bot.send_photo(chat_id=config.reviews_channel_id,
                                     photo=review.photo_file_id, caption=text)
            else:
                await bot.send_message(chat_id=config.reviews_channel_id, text=text)
        except Exception as exc:
            logger.error("publish review to channel: %s", exc)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=review_admin_keyboard(review_id, "APPROVED")
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("review_reject:"))
async def admin_reject_review(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    review_id = int(callback.data.split(":")[1])
    review = await reject_review(session, review_id)
    if review is None:
        await callback.answer("⚠️ Отзыв не найден.", show_alert=True)
        return
    await session.commit()
    await callback.answer("❌ Отзыв отклонён.", show_alert=True)
    try:
        await bot.send_message(chat_id=review.telegram_id,
                               text="❌ <b>Ваш отзыв не прошёл модерацию.</b>", parse_mode="HTML")
    except Exception:
        pass
    try:
        await callback.message.edit_reply_markup(
            reply_markup=review_admin_keyboard(review_id, "REJECTED")
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("review_delete:"))
async def admin_delete_review(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _check_access(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    from app.services import delete_review as del_review
    deleted = await del_review(session, int(callback.data.split(":")[1]))
    await session.commit()
    if deleted:
        await callback.answer("🗑 Удалён.", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer("⚠️ Не найден.", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПОДДЕРЖКА
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "🎫 Поддержка")
async def admin_support_menu(message: Message, session: AsyncSession) -> None:
    if not await _check_manager_access(message.from_user.id, session):
        return
    await message.answer("🎫 <b>Обращения</b>\n\nВыберите фильтр:",
                         parse_mode="HTML", reply_markup=support_filter_keyboard())


@router.callback_query(F.data.startswith("tickets_filter:"))
async def admin_tickets_filtered(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_manager_access(callback.from_user.id, session):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    f = callback.data.split(":")[1]
    status_map = {"NEW": TicketStatus.NEW, "OPEN": TicketStatus.OPEN, "CLOSED": TicketStatus.CLOSED, "ALL": None}
    tickets = await get_all_tickets(session, status_filter=status_map.get(f), limit=20)
    if not tickets:
        await callback.answer("Обращений не найдено.", show_alert=True)
        return
    status_icons = {TicketStatus.NEW: "🆕", TicketStatus.OPEN: "🔓", TicketStatus.CLOSED: "🔒"}
    label = {"NEW": "🆕 Новые", "OPEN": "🔓 Открытые", "CLOSED": "🔒 Закрытые", "ALL": "📋 Все"}.get(f, "")
    lines = [f"🎫 <b>{label}</b> ({len(tickets)} шт.)\n"]
    for t in tickets:
        icon = status_icons.get(t.status, "💬")
        lines.append(f"{icon} <b>{t.ticket_number}</b>\n   {t.subject[:40]}\n   👤 {t.user.mention}")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    for t in tickets[:5]:
        is_closed = t.status == TicketStatus.CLOSED
        last_msg = t.messages[-1].text[:100] if t.messages else "(нет сообщений)"
        icon = status_icons.get(t.status, "💬")
        await callback.message.answer(
            f"🎫 <b>{t.ticket_number}</b>  {icon}\nТема: {t.subject}\n👤 {t.user.mention}\n\n{last_msg}",
            parse_mode="HTML",
            reply_markup=ticket_admin_keyboard(t.id, is_closed),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_reply_ticket:"))
async def admin_reply_ticket_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _check_access(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    ticket_id = int(callback.data.split(":")[1])
    await state.set_state(AdminFSM.replying_to_ticket)
    await state.update_data(reply_ticket_id=ticket_id)
    await callback.message.answer("✏️ Введите ответ клиенту:", reply_markup=cancel_admin_keyboard())
    await callback.answer()


@router.message(AdminFSM.replying_to_ticket, F.text)
async def admin_send_ticket_reply(message: Message, state: FSMContext,
                                  session: AsyncSession, bot: Bot) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    data = await state.get_data()
    ticket = await get_ticket_by_id(session, data["reply_ticket_id"])
    await state.clear()
    if ticket is None:
        await message.answer("⚠️ Обращение не найдено.", reply_markup=admin_main_keyboard())
        return
    await add_ticket_message(session, ticket.id, message.text, "admin")
    await session.commit()
    try:
        await bot.send_message(
            chat_id=ticket.user.telegram_id,
            text=f"📩 <b>Ответ менеджера</b>\n\n🎫 <b>{ticket.ticket_number}</b>\n"
                 f"Тема: {ticket.subject}\n\n💬 {message.text}",
            parse_mode="HTML",
            reply_markup=ticket_reply_keyboard(ticket.id),
        )
        await message.answer("✅ Ответ отправлен.", reply_markup=admin_main_keyboard())
    except Exception as exc:
        logger.error("send ticket reply: %s", exc)
        await message.answer("⚠️ Не удалось доставить ответ.", reply_markup=admin_main_keyboard())


@router.callback_query(F.data.startswith("ticket_close:"))
async def admin_close_ticket(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    ticket_id = int(callback.data.split(":")[1])
    ticket = await close_ticket(session, ticket_id)
    if ticket is None:
        await callback.answer("⚠️ Не найдено.", show_alert=True)
        return
    await session.commit()
    try:
        await bot.send_message(chat_id=ticket.user.telegram_id,
                               text=f"🔒 <b>Обращение {ticket.ticket_number} закрыто.</b>\n\n"
                                    "Если остались вопросы — создайте новое обращение.", parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("🔒 Закрыто.", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=ticket_admin_keyboard(ticket_id, True))
    except Exception:
        pass


@router.callback_query(F.data.startswith("ticket_reopen:"))
async def admin_reopen_ticket(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    ticket_id = int(callback.data.split(":")[1])
    ticket = await reopen_ticket(session, ticket_id)
    if ticket is None:
        await callback.answer("⚠️ Не найдено.", show_alert=True)
        return
    await session.commit()
    try:
        await bot.send_message(chat_id=ticket.user.telegram_id,
                               text=f"🔓 <b>Обращение {ticket.ticket_number} переоткрыто.</b>",
                               parse_mode="HTML")
    except Exception:
        pass
    await callback.answer("🔓 Переоткрыто.", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=ticket_admin_keyboard(ticket_id, False))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# МЕНЕДЖЕРЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "👥 Менеджеры")
async def admin_managers_list(message: Message, session: AsyncSession) -> None:
    if not _check_access(message.from_user.id):
        return
    managers = await get_all_managers(session)
    if not managers:
        await message.answer("👥 Менеджеров пока нет.\n\nДобавить: нажмите «Добавить менеджера»")
        return
    lines = [f"👥 <b>Менеджеры</b> ({len(managers)} чел.)\n"]
    for mgr in managers:
        role_icon = "👑" if mgr.role == ManagerRole.ADMIN else "👤"
        status = "✅" if mgr.is_active else "❌"
        lines.append(f"{status} {role_icon} {mgr.mention} ({mgr.role.value})\nID: <code>{mgr.telegram_id}</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить менеджера", callback_data="manager_add"))
    await message.answer("Действия:", reply_markup=builder.as_markup())


@router.callback_query(F.data == "manager_add")
async def admin_add_manager_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _check_access(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    await state.set_state(AdminFSM.adding_manager_id)
    await callback.message.answer(
        "👤 <b>Добавление менеджера</b>\n\n"
        "Отправьте Telegram ID нового менеджера.\n"
        "(Попросите менеджера написать @userinfobot)\n\n"
        "Для выдачи прав администратора добавьте «:admin» в конце: <code>123456789:admin</code>",
        parse_mode="HTML", reply_markup=cancel_admin_keyboard(),
    )
    await callback.answer()


@router.message(AdminFSM.adding_manager_id, F.text)
async def admin_add_manager(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    text = message.text.strip()
    role = ManagerRole.ADMIN if text.endswith(":admin") else ManagerRole.MANAGER
    tg_id_str = text.replace(":admin", "").strip()
    if not tg_id_str.isdigit():
        await message.answer("⚠️ Введите числовой Telegram ID.", reply_markup=cancel_admin_keyboard())
        return
    tg_id = int(tg_id_str)
    try:
        tg_user = await bot.get_chat(tg_id)
        first_name = tg_user.first_name or "Менеджер"
        username = tg_user.username
    except Exception:
        first_name = "Менеджер"
        username = None
    manager = await add_manager(session, tg_id, first_name, username, role, message.from_user.id)
    await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Менеджер добавлен!\n\n"
        f"👤 {manager.mention}\nРоль: {manager.role.value}\nID: <code>{tg_id}</code>",
        parse_mode="HTML", reply_markup=admin_main_keyboard(),
    )


@router.callback_query(F.data.startswith("manager_remove:"))
async def admin_remove_manager(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _check_access(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    tg_id = int(callback.data.split(":")[1])
    manager = await deactivate_manager(session, tg_id)
    await session.commit()
    if manager:
        await callback.answer(f"✅ Менеджер {manager.mention} деактивирован.", show_alert=True)
    else:
        await callback.answer("⚠️ Не найден.", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОМОКОДЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "🎟 Промокоды")
async def admin_promos_list(message: Message, session: AsyncSession) -> None:
    if not _check_access(message.from_user.id):
        return
    from app.services import get_all_promos
    promos = await get_all_promos(session)
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    if not promos:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="➕ Создать промокод", callback_data="promo_create"))
        await message.answer("🎟 Промокодов пока нет.", reply_markup=builder.as_markup())
        return

    lines = [f"🎟 <b>Промокоды</b> ({len(promos)} шт.)\n"]
    for p in promos:
        status = "✅ Активен" if not p.is_used else "❌ Использован"
        if p.discount_type == "percent":
            discount_label = f"{p.discount_percent}%"
        else:
            discount_label = f"{p.discount_fixed:.0f} ₽ фикс."
        exp = p.expires_at.strftime("%d.%m.%Y") if p.expires_at else "∞"
        lines.append(
            f"<code>{p.code}</code> — {discount_label} | {status} | до {exp}"
        )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Создать промокод", callback_data="promo_create"))
    for p in promos:
        builder.row(
            InlineKeyboardButton(
                text=f"🗑 Удалить {p.code}",
                callback_data=f"promo_delete:{p.id}",
            )
        )
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data == "promo_create")
async def admin_promo_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _check_access(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    await state.set_state(AdminFSM.creating_promo_code)
    await callback.message.answer(
        "🎟 <b>Создание промокода</b>\n\n"
        "Введите код промокода (только латинские буквы и цифры, например: <code>SALE2024</code>).\n"
        "Или отправьте <b>авто</b> для генерации случайного кода.",
        parse_mode="HTML",
        reply_markup=cancel_admin_keyboard(),
    )
    await callback.answer()


@router.message(AdminFSM.creating_promo_code, F.text)
async def admin_promo_enter_code(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    if message.text.lower() == "авто":
        from app.services import generate_unique_code
        code = await generate_unique_code(session)
    else:
        code = message.text.strip().upper()
        if not code.replace("-", "").isalnum():
            await message.answer("⚠️ Код может содержать только буквы и цифры.", reply_markup=cancel_admin_keyboard())
            return

    await state.update_data(new_promo_code=code)
    await state.set_state(AdminFSM.creating_promo_type)

    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="% Процент", callback_data="promo_type:percent"),
        InlineKeyboardButton(text="₽ Фикс. сумма", callback_data="promo_type:fixed"),
    )
    await message.answer(
        f"✅ Код: <code>{code}</code>\n\nВыберите тип скидки:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(AdminFSM.creating_promo_type, F.data.startswith("promo_type:"))
async def admin_promo_choose_type(callback: CallbackQuery, state: FSMContext) -> None:
    promo_type = callback.data.split(":")[1]
    await state.update_data(new_promo_type=promo_type)
    await state.set_state(AdminFSM.creating_promo_value)
    label = "процент скидки (например: 10)" if promo_type == "percent" else "сумму скидки в рублях (например: 500)"
    await callback.message.answer(
        f"Введите {label}:",
        reply_markup=cancel_admin_keyboard(),
    )
    await callback.answer()


@router.message(AdminFSM.creating_promo_value, F.text)
async def admin_promo_enter_value(message: Message, state: FSMContext,
                                  session: AsyncSession) -> None:
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=admin_main_keyboard())
        return
    try:
        value = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("⚠️ Введите число.", reply_markup=cancel_admin_keyboard())
        return

    data = await state.get_data()
    from app.services import create_admin_promo
    promo, err = await create_admin_promo(
        session=session,
        code=data["new_promo_code"],
        discount_type=data["new_promo_type"],
        discount_value=value,
        created_by=message.from_user.id,
    )
    await state.clear()

    if err:
        await message.answer(f"⚠️ {err}", parse_mode="HTML", reply_markup=admin_main_keyboard())
        return

    await session.commit()
    label = f"{value}%" if data["new_promo_type"] == "percent" else f"{value:.2f} ₽"
    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"Код: <code>{promo.code}</code>\n"
        f"Скидка: <b>{label}</b>\n"
        f"Статус: ✅ Активен",
        parse_mode="HTML",
        reply_markup=admin_main_keyboard(),
    )


@router.callback_query(F.data.startswith("promo_delete:"))
async def admin_promo_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _check_access(callback.from_user.id):
        await callback.answer("🚫 Доступ запрещён.", show_alert=True)
        return
    promo_id = int(callback.data.split(":")[1])
    from app.services import delete_promo
    deleted = await delete_promo(session, promo_id)
    await session.commit()
    if deleted:
        await callback.answer("🗑 Промокод удалён.", show_alert=True)
        try:
            await callback.message.delete()
        except Exception:
            pass
    else:
        await callback.answer("⚠️ Промокод не найден.", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
# РЕФЕРАЛЫ
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "💰 Рефералы")
async def admin_referrals(message: Message, session: AsyncSession) -> None:
    if not _check_access(message.from_user.id):
        return
    from sqlalchemy import select, func
    from app.models import User, BonusTransaction, BonusOperationType
    result = await session.execute(
        select(User).where(User.referrer_id.isnot(None)).order_by(User.created_at.desc()).limit(20)
    )
    referred = result.scalars().all()
    total_rewards = (await session.execute(
        select(func.sum(BonusTransaction.amount))
        .where(BonusTransaction.operation_type == BonusOperationType.REFERRAL_REWARD)
    )).scalar_one() or 0.0
    lines = [
        f"💰 <b>Реферальная статистика</b>\n",
        f"👥 Приглашено пользователей: <b>{len(referred)}</b>",
        f"💎 Выплачено вознаграждений: <b>{total_rewards:.2f} ₽</b>",
        "",
    ]
    if referred:
        lines.append("<b>Последние 20 приглашённых:</b>")
        for u in referred:
            lines.append(f"• {u.full_name} — {u.created_at.strftime('%d.%m.%Y')}")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ═══════════════════════════════════════════════════════════════════════════════
# ИЗБРАННОЕ ПОЛЬЗОВАТЕЛЕЙ (admin view)
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "❤️ Избранное польз.")
async def admin_favorites_stats(message: Message, session: AsyncSession) -> None:
    if not _check_access(message.from_user.id):
        return
    from sqlalchemy import select, func
    from app.models import Favorite, FavoriteCategory
    total = (await session.execute(select(func.count()).select_from(Favorite))).scalar_one()
    lines = [f"❤️ <b>Избранное пользователей</b>\n", f"Всего сохранений: <b>{total}</b>\n"]
    for cat in FavoriteCategory:
        count = (await session.execute(
            select(func.count()).select_from(Favorite).where(Favorite.category == cat)
        )).scalar_one()
        if count > 0:
            lines.append(f"  {cat.value}: {count}")
    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── Возврат в меню для администратора ──────────────────────────────────────

@router.message(F.text == "◀️ Главное меню")
async def admin_back_to_menu(message: Message, session: AsyncSession) -> None:
    if is_admin(message.from_user.id) or await _check_manager_access(message.from_user.id, session):
        await message.answer("🔧 Панель управления:", reply_markup=admin_main_keyboard())
    else:
        from app.keyboards.client import main_menu_keyboard as client_main
        await message.answer("Главное меню:", reply_markup=client_main())


# ═══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ
# ═══════════════════════════════════════════════════════════════════════════════

async def _send_order_card_to_admin(message: Message, order) -> None:
    text = format_order_card(order, for_admin=True)
    keyboard = order_admin_keyboard(order.id, order.order_number)
    photos = [img.file_id for img in order.images]
    if photos:
        if len(photos) == 1:
            await message.answer_photo(photo=photos[0], caption=text, parse_mode="HTML", reply_markup=keyboard)
        else:
            media = [
                InputMediaPhoto(media=fid, caption=text if i == 0 else None,
                                parse_mode="HTML" if i == 0 else None)
                for i, fid in enumerate(photos[:10])
            ]
            await message.answer_media_group(media=media)
            await message.answer(f"📦 Управление <b>{order.order_number}</b>:",
                                 parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
