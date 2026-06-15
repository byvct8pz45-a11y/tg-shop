from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot
from aiogram.types import InputMediaPhoto

from app.models import Order, OrderStatus
from config import config

logger = logging.getLogger(__name__)

STATUS_EMOJI = {
    OrderStatus.NEW: "🆕",
    OrderStatus.CALCULATING: "🧮",
    OrderStatus.AWAITING_APPROVAL: "⏳",
    OrderStatus.AWAITING_PAYMENT: "💳",
    OrderStatus.PAID: "✅",
    OrderStatus.PURCHASED: "🛒",
    OrderStatus.IN_TRANSIT: "🚚",
    OrderStatus.RECEIVED: "📬",
    OrderStatus.COMPLETED: "🎉",
    OrderStatus.CANCELLED: "❌",
}


def is_admin(user_id: int) -> bool:
    return user_id in config.admin_ids


def format_order_card(order: Order, for_admin: bool = False) -> str:
    emoji = STATUS_EMOJI.get(order.status, "📦")
    lines = [
        f"📦 <b>Заказ {order.order_number}</b>",
        f"📊 Статус: {emoji} {order.status.value}",
        f"📅 Создан: {order.created_at.strftime('%d.%m.%Y %H:%M')}",
        "",
        "📝 <b>Описание:</b>",
        order.description,
    ]
    if order.found_price:
        lines += ["", f"💰 <b>Найденная цена:</b> {order.found_price}"]
    if order.desired_budget:
        lines += [f"🎯 <b>Желаемый бюджет:</b> {order.desired_budget}"]

    if order.item_price is not None:
        lines += [
            "",
            "🧮 <b>Расчёт стоимости:</b>",
            f"  Товар: <b>{order.item_price:.2f} ₽</b>",
            f"  Доставка: <b>{order.delivery_price:.2f} ₽</b>",
            f"  Комиссия: <b>{order.commission:.2f} ₽</b>",
        ]
        if order.discount_amount > 0:
            lines.append(f"  Скидка: <b>-{order.discount_amount:.2f} ₽</b>")
        if order.bonus_used > 0:
            lines.append(f"  Бонусы: <b>-{order.bonus_used:.2f} ₽</b>")
        if order.total_price is not None:
            lines.append(f"  <b>Итого: {order.total_price:.2f} ₽</b>")

    if order.promo_code:
        lines += [f"🎟 Промокод: <code>{order.promo_code}</code>"]

    if for_admin and order.user:
        user = order.user
        lines += [
            "",
            "👤 <b>Клиент:</b>",
            f"  ID: <code>{user.telegram_id}</code>",
            f"  Имя: {user.full_name}",
            f"  Username: {user.mention}",
        ]
        if order.manager:
            lines.append(f"  Менеджер: {order.manager.mention}")
        if order.cancel_reason:
            lines += ["", f"❌ <b>Причина отказа:</b> {order.cancel_reason}"]

    return "\n".join(lines)


def format_pricing_card(order: Order) -> str:
    """Карточка расчёта стоимости для отправки клиенту."""
    lines = [
        f"💰 <b>Расчёт стоимости заказа {order.order_number}</b>",
        "",
        f"  Товар: <b>{order.item_price:.2f} ₽</b>",
        f"  Доставка: <b>{order.delivery_price:.2f} ₽</b>",
        f"  Комиссия: <b>{order.commission:.2f} ₽</b>",
    ]
    if order.discount_amount > 0:
        lines.append(f"  Скидка: <b>-{order.discount_amount:.2f} ₽</b>")
    if order.bonus_used > 0:
        lines.append(f"  Бонусы: <b>-{order.bonus_used:.2f} ₽</b>")
    lines += [
        "",
        f"  <b>Итого к оплате: {order.total_price:.2f} ₽</b>",
    ]
    return "\n".join(lines)


async def notify_admins_new_order(bot: Bot, order: Order) -> None:
    from app.keyboards.admin import order_admin_keyboard
    text = "🔔 <b>Новый заказ!</b>\n\n" + format_order_card(order, for_admin=True)
    keyboard = order_admin_keyboard(order.id, order.order_number)
    photo_ids = [img.file_id for img in order.images]

    for admin_id in config.admin_ids:
        try:
            if photo_ids:
                if len(photo_ids) == 1:
                    await bot.send_photo(chat_id=admin_id, photo=photo_ids[0], caption=text, parse_mode="HTML", reply_markup=keyboard)
                else:
                    media = [InputMediaPhoto(media=fid, caption=text if i == 0 else None, parse_mode="HTML" if i == 0 else None) for i, fid in enumerate(photo_ids[:10])]
                    await bot.send_media_group(chat_id=admin_id, media=media)
                    await bot.send_message(chat_id=admin_id, text=f"📦 Управление заказом <b>{order.order_number}</b>:", parse_mode="HTML", reply_markup=keyboard)
            else:
                await bot.send_message(chat_id=admin_id, text=text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as exc:
            logger.error("Failed to notify admin %s: %s", admin_id, exc)


async def notify_client_status_change(bot: Bot, order: Order) -> None:
    emoji = STATUS_EMOJI.get(order.status, "📦")
    text = (
        f"🔔 <b>Статус вашего заказа изменён</b>\n\n"
        f"📦 Заказ: <b>{order.order_number}</b>\n"
        f"📊 Новый статус: {emoji} <b>{order.status.value}</b>"
    )
    try:
        await bot.send_message(chat_id=order.user.telegram_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.error("Failed to notify client %s: %s", order.user.telegram_id, exc)


async def notify_managers_new_order(bot: Bot, order: Order, session) -> None:
    """Уведомить всех активных менеджеров о новом заказе."""
    from app.keyboards.admin import order_admin_keyboard
    from app.models import Manager
    from sqlalchemy import select
    result = await session.execute(select(Manager).where(Manager.is_active == True))
    managers = result.scalars().all()

    text = "🔔 <b>Новый заказ!</b>\n\n" + format_order_card(order, for_admin=True)
    keyboard = order_admin_keyboard(order.id, order.order_number)

    for mgr in managers:
        if mgr.telegram_id in config.admin_ids:
            continue  # администраторы уже получают уведомление через notify_admins_new_order
        try:
            await bot.send_message(chat_id=mgr.telegram_id, text=text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as exc:
            logger.error("Failed to notify manager %s: %s", mgr.telegram_id, exc)
