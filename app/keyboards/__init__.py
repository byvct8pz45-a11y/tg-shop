from .client import (
    main_menu_keyboard, cancel_keyboard, photo_upload_keyboard,
    order_preview_keyboard, bonus_use_keyboard, my_orders_keyboard,
    review_action_keyboard, rating_keyboard,
    review_photo_keyboard, review_confirm_keyboard,
    pricing_response_keyboard, receipt_keyboard, receipt_admin_keyboard,
    support_menu_keyboard, my_tickets_keyboard, ticket_reply_keyboard,
    favorites_category_keyboard, favorite_item_keyboard,
    add_to_favorite_keyboard, remove_keyboard,
)
from .admin import (
    admin_main_keyboard, cancel_admin_keyboard, order_admin_keyboard,
    status_change_keyboard, pricing_confirm_keyboard, review_admin_keyboard,
    ticket_admin_keyboard, support_filter_keyboard, manager_action_keyboard,
    orders_filter_keyboard,
)

__all__ = [
    # client
    "main_menu_keyboard", "cancel_keyboard", "photo_upload_keyboard",
    "order_preview_keyboard", "bonus_use_keyboard", "my_orders_keyboard",
    "review_action_keyboard", "rating_keyboard",
    "review_photo_keyboard", "review_confirm_keyboard",
    "pricing_response_keyboard", "receipt_keyboard", "receipt_admin_keyboard",
    "support_menu_keyboard", "my_tickets_keyboard", "ticket_reply_keyboard",
    "favorites_category_keyboard", "favorite_item_keyboard",
    "add_to_favorite_keyboard", "remove_keyboard",
    # admin
    "admin_main_keyboard", "cancel_admin_keyboard", "order_admin_keyboard",
    "status_change_keyboard", "pricing_confirm_keyboard", "review_admin_keyboard",
    "ticket_admin_keyboard", "support_filter_keyboard", "manager_action_keyboard",
    "orders_filter_keyboard",
]
