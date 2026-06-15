from .user_service import get_or_create_user, get_user_by_telegram_id, get_all_users
from .order_service import (
    create_order, get_order_by_number, get_order_by_id,
    get_orders_by_user, get_recent_orders, update_order_status,
    set_order_pricing, set_order_cancel_reason, assign_manager,
    save_message, get_stats,
)
from .settings_service import get_welcome_text, set_setting, get_setting, get_payment_details
from .review_service import (
    create_review, get_published_reviews, get_all_reviews, get_pending_reviews,
    get_review_by_id, approve_review, reject_review, delete_review,
    get_user_review_for_order,
)
from .support_service import (
    create_ticket, get_ticket_by_id, get_tickets_by_user,
    get_all_tickets, add_ticket_message, close_ticket, reopen_ticket,
)
from .manager_service import (
    get_manager_by_telegram_id, get_all_managers, add_manager,
    deactivate_manager, is_manager_or_admin, is_admin_role,
)
from .promo_service import (
    issue_first_order_promo, get_promo_by_code, validate_promo,
    validate_promo_for_order, use_promo, get_user_promos, get_all_promos,
    create_admin_promo, delete_promo, calculate_promo_discount,
)
from .referral_service import add_bonus, spend_bonus, process_referral_reward
from .favorite_service import (
    add_favorite, remove_favorite, get_user_favorites,
    get_favorite_by_id, search_favorites,
)

__all__ = [
    # users
    "get_or_create_user", "get_user_by_telegram_id", "get_all_users",
    # orders
    "create_order", "get_order_by_number", "get_order_by_id",
    "get_orders_by_user", "get_recent_orders", "update_order_status",
    "set_order_pricing", "set_order_cancel_reason", "assign_manager",
    "save_message", "get_stats",
    # settings
    "get_welcome_text", "set_setting", "get_setting", "get_payment_details",
    # reviews
    "create_review", "get_published_reviews", "get_all_reviews", "get_pending_reviews",
    "get_review_by_id", "approve_review", "reject_review", "delete_review",
    "get_user_review_for_order",
    # support
    "create_ticket", "get_ticket_by_id", "get_tickets_by_user",
    "get_all_tickets", "add_ticket_message", "close_ticket", "reopen_ticket",
    # managers
    "get_manager_by_telegram_id", "get_all_managers", "add_manager",
    "deactivate_manager", "is_manager_or_admin", "is_admin_role",
    # promos
    "issue_first_order_promo", "get_promo_by_code", "validate_promo",
    "validate_promo_for_order", "use_promo", "get_user_promos", "get_all_promos",
    "create_admin_promo", "delete_promo", "calculate_promo_discount",
    # referral & bonus
    "add_bonus", "spend_bonus", "process_referral_reward",
    # favorites
    "add_favorite", "remove_favorite", "get_user_favorites",
    "get_favorite_by_id", "search_favorites",
]
