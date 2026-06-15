from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.models import OrderStatus


def admin_main_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📋 Заказы"), KeyboardButton(text="📊 Статистика"))
    builder.row(KeyboardButton(text="⭐ Отзывы"), KeyboardButton(text="🎫 Поддержка"))
    builder.row(KeyboardButton(text="👥 Менеджеры"), KeyboardButton(text="🎟 Промокоды"))
    builder.row(KeyboardButton(text="💰 Рефералы"), KeyboardButton(text="❤️ Избранное польз."))
    builder.row(KeyboardButton(text="✏️ Приветствие"), KeyboardButton(text="💳 Реквизиты"))
    return builder.as_markup(resize_keyboard=True)


def cancel_admin_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="❌ Отмена"))
    return builder.as_markup(resize_keyboard=True)


def order_admin_keyboard(order_id: int, order_number: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Статус", callback_data=f"admin_status:{order_id}"),
        InlineKeyboardButton(text="🧮 Расчёт", callback_data=f"admin_calc:{order_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="✉️ Написать клиенту", callback_data=f"admin_reply:{order_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"admin_close:{order_id}"),
    )
    return builder.as_markup()


def status_change_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    statuses = [
        (OrderStatus.NEW, "🆕 Новый"),
        (OrderStatus.CALCULATING, "🧮 Расчёт стоимости"),
        (OrderStatus.AWAITING_APPROVAL, "⏳ Ожидает согласования"),
        (OrderStatus.AWAITING_PAYMENT, "💳 Ожидает оплаты"),
        (OrderStatus.PAID, "✅ Оплачен"),
        (OrderStatus.PURCHASED, "🛒 Выкуплен"),
        (OrderStatus.IN_TRANSIT, "🚚 В пути"),
        (OrderStatus.RECEIVED, "📬 Получен"),
        (OrderStatus.COMPLETED, "🎉 Завершён"),
        (OrderStatus.CANCELLED, "❌ Отменён"),
    ]
    for status, label in statuses:
        builder.row(
            InlineKeyboardButton(
                text=label,
                callback_data=f"set_status:{order_id}:{status.name}",
            )
        )
    return builder.as_markup()


def pricing_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить комиссию", callback_data=f"edit_commission:{order_id}"),
        InlineKeyboardButton(text="📤 Отправить клиенту", callback_data=f"send_pricing:{order_id}"),
    )
    return builder.as_markup()


def review_admin_keyboard(review_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == "PENDING":
        builder.row(
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"review_approve:{review_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"review_reject:{review_id}"),
        )
    elif status == "APPROVED":
        builder.row(
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"review_reject:{review_id}"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"review_approve:{review_id}"),
        )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"review_delete:{review_id}"),
    )
    return builder.as_markup()


def ticket_admin_keyboard(ticket_id: int, is_closed: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✉️ Ответить", callback_data=f"admin_reply_ticket:{ticket_id}"),
    )
    if is_closed:
        builder.row(
            InlineKeyboardButton(text="🔓 Переоткрыть", callback_data=f"ticket_reopen:{ticket_id}"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"ticket_close:{ticket_id}"),
        )
    return builder.as_markup()


def support_filter_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🆕 Новые", callback_data="tickets_filter:NEW"),
        InlineKeyboardButton(text="🔓 Открытые", callback_data="tickets_filter:OPEN"),
    )
    builder.row(
        InlineKeyboardButton(text="🔒 Закрытые", callback_data="tickets_filter:CLOSED"),
        InlineKeyboardButton(text="📋 Все", callback_data="tickets_filter:ALL"),
    )
    return builder.as_markup()


def manager_action_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"manager_remove:{telegram_id}"),
    )
    return builder.as_markup()


def orders_filter_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🆕 Новые", callback_data="orders_filter:NEW"),
        InlineKeyboardButton(text="⚙️ Активные", callback_data="orders_filter:ACTIVE"),
    )
    builder.row(
        InlineKeyboardButton(text="🎉 Завершённые", callback_data="orders_filter:COMPLETED"),
        InlineKeyboardButton(text="📋 Все", callback_data="orders_filter:ALL"),
    )
    return builder.as_markup()
