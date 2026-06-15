from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from app.models import FavoriteCategory


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📦 Создать заказ"), KeyboardButton(text="📋 Мои заказы"))
    builder.row(KeyboardButton(text="⭐ Отзывы"), KeyboardButton(text="💬 Поддержка"))
    builder.row(KeyboardButton(text="❤️ Избранное"), KeyboardButton(text="👤 Профиль"))
    return builder.as_markup(resize_keyboard=True)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Отмена + Главное меню — доступны из любого FSM-состояния."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="❌ Отмена"), KeyboardButton(text="🏠 Главное меню"))
    return builder.as_markup(resize_keyboard=True)


def photo_upload_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="✅ Готово"))
    builder.row(KeyboardButton(text="❌ Отмена"), KeyboardButton(text="🏠 Главное меню"))
    return builder.as_markup(resize_keyboard=True)


def order_preview_keyboard(order_temp_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"order_confirm:{order_temp_id}"))
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить", callback_data=f"order_edit:{order_temp_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"order_cancel:{order_temp_id}"),
    )
    return builder.as_markup()


def bonus_use_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Использовать бонусы", callback_data="bonus_use:yes"),
        InlineKeyboardButton(text="❌ Нет", callback_data="bonus_use:no"),
    )
    return builder.as_markup()


def my_orders_keyboard(orders: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        builder.row(
            InlineKeyboardButton(
                text=f"{order.order_number} — {order.status.value}",
                callback_data=f"view_order:{order.id}",
            )
        )
    return builder.as_markup()


def review_action_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data=f"leave_review:{order_id}"),
    )
    return builder.as_markup()


def rating_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⭐ 1", callback_data="rating:1"),
        InlineKeyboardButton(text="⭐⭐ 2", callback_data="rating:2"),
        InlineKeyboardButton(text="⭐⭐⭐ 3", callback_data="rating:3"),
        InlineKeyboardButton(text="⭐⭐⭐⭐ 4", callback_data="rating:4"),
        InlineKeyboardButton(text="⭐⭐⭐⭐⭐ 5", callback_data="rating:5"),
    )
    return builder.as_markup()


def review_photo_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="⏭ Пропустить фото"))
    builder.row(KeyboardButton(text="❌ Отмена"), KeyboardButton(text="🏠 Главное меню"))
    return builder.as_markup(resize_keyboard=True)


def review_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Отправить", callback_data="review_confirm:yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="review_confirm:no"),
    )
    return builder.as_markup()


def pricing_response_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Кнопки после получения расчёта стоимости: согласие, промокод, отказ."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Согласен", callback_data=f"pricing_agree:{order_id}"),
        InlineKeyboardButton(text="❌ Отказаться", callback_data=f"pricing_decline:{order_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🎟 Использовать промокод", callback_data=f"apply_promo:{order_id}"),
    )
    return builder.as_markup()


def receipt_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура при ожидании чека."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🏠 Главное меню"))
    return builder.as_markup(resize_keyboard=True)


def receipt_admin_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Кнопки для менеджера после получения чека."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"payment_confirm:{order_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"payment_reject:{order_id}"),
    )
    return builder.as_markup()


def support_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📝 Новое обращение"))
    builder.row(KeyboardButton(text="📂 Мои обращения"))
    builder.row(KeyboardButton(text="🏠 Главное меню"))
    return builder.as_markup(resize_keyboard=True)


def my_tickets_keyboard(tickets: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status_icons = {"Новый": "🆕", "Открытый": "🔓", "Закрытый": "🔒"}
    for ticket in tickets:
        icon = status_icons.get(ticket.status.value, "💬")
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} {ticket.ticket_number} — {ticket.subject[:30]}",
                callback_data=f"view_ticket:{ticket.id}",
            )
        )
    return builder.as_markup()


def ticket_reply_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✉️ Ответить", callback_data=f"client_reply_ticket:{ticket_id}"),
    )
    return builder.as_markup()


def favorites_category_keyboard(counts: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in FavoriteCategory:
        count = counts.get(cat.name, 0)
        builder.row(
            InlineKeyboardButton(
                text=f"{cat.value} ({count})",
                callback_data=f"fav_cat:{cat.name}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="📋 Все", callback_data="fav_cat:ALL"),
        InlineKeyboardButton(text="🔍 Поиск", callback_data="fav_search"),
    )
    return builder.as_markup()


def favorite_item_keyboard(fav_id: int, channel_id: int, post_id: int) -> InlineKeyboardMarkup:
    channel_str = str(abs(channel_id))
    if channel_str.startswith("100"):
        channel_str = channel_str[3:]
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔗 Открыть пост", url=f"https://t.me/c/{channel_str}/{post_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="📂 Изменить категорию", callback_data=f"fav_setcat:{fav_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🗑 Удалить из избранного", callback_data=f"fav_remove:{fav_id}"),
    )
    return builder.as_markup()


def favorite_category_select_keyboard(fav_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора новой категории для записи в избранном."""
    builder = InlineKeyboardBuilder()
    for cat in FavoriteCategory:
        builder.row(
            InlineKeyboardButton(
                text=cat.value,
                callback_data=f"fav_cat_set:{fav_id}:{cat.name}",
            )
        )
    return builder.as_markup()


def add_to_favorite_keyboard(post_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❤️ Добавить в избранное", callback_data=f"fav_add:{post_id}"),
    )
    return builder.as_markup()


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()
