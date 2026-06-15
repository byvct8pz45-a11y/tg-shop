from aiogram.fsm.state import State, StatesGroup


class OrderFSM(StatesGroup):
    uploading_photos = State()
    entering_description = State()
    entering_found_price = State()
    entering_desired_budget = State()
    choosing_bonus = State()
    preview = State()
    # Отказ клиента
    entering_cancel_reason = State()
    # Промокод после получения расчёта
    entering_promo_code = State()
    # Ожидание чека об оплате
    awaiting_receipt = State()


class AdminFSM(StatesGroup):
    replying_to_client = State()
    setting_welcome = State()
    entering_order_number = State()
    replying_to_ticket = State()
    # Расчёт стоимости
    entering_item_price = State()
    entering_delivery_price = State()
    editing_commission = State()
    # Реквизиты
    setting_payment_details = State()
    # Менеджеры
    adding_manager_id = State()
    # Создание промокода
    creating_promo_code = State()
    creating_promo_type = State()
    creating_promo_value = State()


class ReviewFSM(StatesGroup):
    choosing_rating = State()
    entering_text = State()
    uploading_photo = State()
    confirming = State()


class SupportFSM(StatesGroup):
    entering_subject = State()
    entering_message = State()
    replying_to_ticket = State()
