"""FSM создания заказа, промокоды, оплата, отправка чека."""
from __future__ import annotations
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards import (
    cancel_keyboard, main_menu_keyboard, order_preview_keyboard,
    photo_upload_keyboard, bonus_use_keyboard, pricing_response_keyboard,
    receipt_keyboard, receipt_admin_keyboard,
)
from app.models import OrderStatus, User
from app.services import (
    create_order, get_order_by_id, validate_promo_for_order, use_promo,
    issue_first_order_promo, spend_bonus, update_order_status,
    get_payment_details, set_order_cancel_reason, calculate_promo_discount,
)
from app.states import OrderFSM
from app.utils import notify_admins_new_order, notify_managers_new_order, format_pricing_card
from config import config

logger = logging.getLogger(__name__)
router = Router()
MAX_PHOTOS = 10


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛОБАЛЬНЫЕ ОБРАБОТЧИКИ ОТМЕНЫ И ГЛАВНОГО МЕНЮ (работают из любого состояния)
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "🏠 Главное меню")
async def go_to_main_menu(message: Message, state: FSMContext) -> None:
    """Из любого состояния — в главное меню."""
    await state.clear()
    await message.answer("🏠 Главное меню", reply_markup=main_menu_keyboard())


@router.message(OrderFSM.uploading_photos, F.text == "❌ Отмена")
@router.message(OrderFSM.entering_description, F.text == "❌ Отмена")
@router.message(OrderFSM.entering_found_price, F.text == "❌ Отмена")
@router.message(OrderFSM.entering_desired_budget, F.text == "❌ Отмена")
@router.message(OrderFSM.entering_cancel_reason, F.text == "❌ Отмена")
@router.message(OrderFSM.entering_promo_code, F.text == "❌ Отмена")
async def cancel_order_fsm(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ Действие отменено.", reply_markup=main_menu_keyboard())


# ═══════════════════════════════════════════════════════════════════════════════
# СОЗДАНИЕ ЗАКАЗА
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(F.text == "📦 Создать заказ")
async def start_order(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OrderFSM.uploading_photos)
    await state.update_data(photos=[], promo_code=None, discount_amount=0.0, bonus_used=0.0)
    await message.answer(
        "📸 <b>Шаг 1 из 4 — Фотографии товара</b>\n\n"
        "Загрузите фото товара (до 10 изображений).\n"
        "Когда все фото загружены — нажмите <b>✅ Готово</b>.",
        parse_mode="HTML", reply_markup=photo_upload_keyboard(),
    )


@router.message(OrderFSM.uploading_photos, F.photo)
async def handle_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    photos: list = data.get("photos", [])
    if len(photos) >= MAX_PHOTOS:
        await message.answer(f"⚠️ Максимум {MAX_PHOTOS} фотографий. Нажмите <b>✅ Готово</b>.", parse_mode="HTML")
        return
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    remaining = MAX_PHOTOS - len(photos)
    await message.answer(
        f"✅ Фото добавлено ({len(photos)}/{MAX_PHOTOS}). "
        + (f"Можно добавить ещё {remaining}." if remaining > 0 else "Достигнут максимум."),
        reply_markup=photo_upload_keyboard(),
    )


@router.message(OrderFSM.uploading_photos, F.text == "✅ Готово")
async def photos_done(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("photos"):
        await message.answer("⚠️ Загрузите хотя бы одно фото.", reply_markup=photo_upload_keyboard())
        return
    await state.set_state(OrderFSM.entering_description)
    await message.answer(
        f"📝 <b>Шаг 2 из 4 — Описание товара</b>\n\nЗагружено фото: {len(data['photos'])}\n\n"
        "Опишите товар: размер, цвет, характеристики, ссылку на товар.",
        parse_mode="HTML", reply_markup=cancel_keyboard(),
    )


@router.message(OrderFSM.uploading_photos)
async def photos_invalid(message: Message) -> None:
    await message.answer("⚠️ Отправьте фото или нажмите <b>✅ Готово</b>.", parse_mode="HTML",
                         reply_markup=photo_upload_keyboard())


@router.message(OrderFSM.entering_description, F.text)
async def handle_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text)
    await state.set_state(OrderFSM.entering_found_price)
    await message.answer(
        "💰 <b>Шаг 3 из 4 — Найденная цена</b>\n\n"
        "Введите цену товара (например: <code>2500 руб</code> или <code>$35</code>).\n"
        "Если цена неизвестна — введите <b>не знаю</b>.",
        parse_mode="HTML", reply_markup=cancel_keyboard(),
    )


@router.message(OrderFSM.entering_found_price, F.text)
async def handle_found_price(message: Message, state: FSMContext) -> None:
    price = None if message.text.lower() in ("не знаю", "-", "0") else message.text
    await state.update_data(found_price=price)
    await state.set_state(OrderFSM.entering_desired_budget)
    await message.answer(
        "🎯 <b>Шаг 4 из 4 — Желаемый бюджет</b>\n\nСколько готовы потратить? Например: <code>до 3000 руб</code>.",
        parse_mode="HTML", reply_markup=cancel_keyboard(),
    )


@router.message(OrderFSM.entering_desired_budget, F.text)
async def handle_desired_budget(message: Message, state: FSMContext, db_user: User) -> None:
    await state.update_data(desired_budget=message.text)
    data = await state.get_data()
    if db_user.bonus_balance > 0:
        await state.set_state(OrderFSM.choosing_bonus)
        await message.answer(
            f"💰 <b>Бонусный баланс</b>\n\n"
            f"У вас есть бонусный баланс: <b>{db_user.bonus_balance:.2f} ₽</b>\n\n"
            "Использовать бонусы для оплаты комиссии?",
            parse_mode="HTML", reply_markup=bonus_use_keyboard(),
        )
        return
    await _show_preview(message, state, data, db_user)


@router.callback_query(OrderFSM.choosing_bonus, F.data.startswith("bonus_use:"))
async def handle_bonus_choice(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    use = callback.data.split(":")[1] == "yes"
    data = await state.get_data()
    if use:
        await state.update_data(use_bonus=True)
    await callback.answer()
    await _show_preview(callback.message, state, data, db_user, use_bonus=use)


async def _show_preview(message: Message, state: FSMContext, data: dict,
                        db_user: User, use_bonus: bool = False) -> None:
    bonus_text = ""
    if use_bonus and db_user.bonus_balance > 0:
        bonus_text = f"\n💰 Будут списаны бонусы: <b>{db_user.bonus_balance:.2f} ₽</b>"
    promo_text = f"\n🎟 Промокод: <code>{data.get('promo_code')}</code>" if data.get("promo_code") else ""
    preview = (
        "👁 <b>Предпросмотр заказа</b>\n\n"
        f"📝 <b>Описание:</b>\n{data['description']}\n\n"
        f"💰 <b>Найденная цена:</b> {data.get('found_price') or 'не указана'}\n"
        f"🎯 <b>Желаемый бюджет:</b> {data.get('desired_budget', '—')}\n"
        f"🖼 <b>Фото:</b> {len(data.get('photos', []))} шт."
        f"{promo_text}{bonus_text}\n\n"
        "Подтвердите заказ:"
    )
    await state.set_state(OrderFSM.preview)
    photos = data.get("photos", [])
    if photos:
        await message.answer_photo(photo=photos[0], caption=preview, parse_mode="HTML",
                                   reply_markup=order_preview_keyboard("new"))
    else:
        await message.answer(preview, parse_mode="HTML", reply_markup=order_preview_keyboard("new"))


@router.callback_query(OrderFSM.preview, F.data.startswith("order_confirm:"))
async def confirm_order(callback: CallbackQuery, state: FSMContext, session: AsyncSession,
                        db_user: User, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()

    discount = 0.0
    promo_obj = None
    # Реферальная скидка — применяется при расчёте цены менеджером
    existing_orders = db_user.orders
    is_first = not any(o.status != OrderStatus.CANCELLED for o in existing_orders)
    if is_first and db_user.referrer_id and not db_user.referral_discount_used:
        db_user.referral_discount_used = True

    promo_code = data.get("promo_code")
    if promo_code:
        promo_obj, err = await validate_promo_for_order(session, promo_code, db_user.id)
        if promo_obj:
            discount = promo_obj.discount_percent if promo_obj.discount_type == "percent" else 0.0

    order = await create_order(
        session=session,
        user_id=db_user.id,
        description=data["description"],
        photo_file_ids=data.get("photos", []),
        found_price=data.get("found_price"),
        desired_budget=data.get("desired_budget"),
        promo_code=promo_code,
        discount_amount=discount,
        bonus_used=0.0,
    )

    if promo_obj:
        await use_promo(session, promo_obj, order.id, db_user.id)

    await session.commit()

    try:
        await callback.message.edit_caption(
            caption=f"✅ <b>Заказ {order.order_number} создан!</b>\n\n"
                    "Менеджеры получили ваш запрос и свяжутся с вами.",
            parse_mode="HTML",
        )
    except Exception:
        try:
            await callback.message.edit_text(
                text=f"✅ <b>Заказ {order.order_number} создан!</b>\n\n"
                     "Менеджеры получили ваш запрос и свяжутся с вами.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await callback.message.answer(
        "📋 Отслеживайте статус в разделе <b>«Мои заказы»</b>.",
        parse_mode="HTML", reply_markup=main_menu_keyboard(),
    )
    await notify_admins_new_order(bot, order)
    await notify_managers_new_order(bot, order, session)
    await callback.answer()


@router.callback_query(OrderFSM.preview, F.data.startswith("order_edit:"))
async def edit_order(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderFSM.uploading_photos)
    await state.update_data(photos=[])
    await callback.message.answer("🔄 Начнём заново.\n\n📸 Загрузите фото товара.",
                                  reply_markup=photo_upload_keyboard())
    await callback.answer()


@router.callback_query(OrderFSM.preview, F.data.startswith("order_cancel:"))
async def cancel_from_preview(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("❌ Создание заказа отменено.", reply_markup=main_menu_keyboard())
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# ПРОМОКОД ПОСЛЕ ПОЛУЧЕНИЯ РАСЧЁТА СТОИМОСТИ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("apply_promo:"))
async def apply_promo_start(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[1])
    await state.set_state(OrderFSM.entering_promo_code)
    await state.update_data(promo_order_id=order_id)
    await callback.message.answer(
        "🎟 <b>Введите промокод:</b>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(OrderFSM.entering_promo_code, F.text)
async def apply_promo_code(message: Message, state: FSMContext,
                           session: AsyncSession, db_user: User) -> None:
    if message.text in ("❌ Отмена", "🏠 Главное меню"):
        await state.clear()
        if message.text == "🏠 Главное меню":
            await message.answer("🏠 Главное меню", reply_markup=main_menu_keyboard())
        else:
            await message.answer("Отменено.", reply_markup=main_menu_keyboard())
        return

    data = await state.get_data()
    order_id = data["promo_order_id"]
    code = message.text.strip().upper()

    promo, err = await validate_promo_for_order(session, code, db_user.id)
    if not promo:
        await message.answer(err, reply_markup=cancel_keyboard())
        return

    # Получаем заказ и пересчитываем
    order = await get_order_by_id(session, order_id)
    if order is None or order.user_id != db_user.id:
        await state.clear()
        await message.answer("⚠️ Заказ не найден.", reply_markup=main_menu_keyboard())
        return

    if order.item_price is None:
        # Цена ещё не рассчитана — сохраняем промокод, применится при расчёте
        order.promo_code = code
        await session.flush()
        await session.commit()
        await state.clear()
        await message.answer(
            f"✅ Промокод <code>{code}</code> сохранён. Скидка будет применена при расчёте стоимости.",
            parse_mode="HTML", reply_markup=main_menu_keyboard(),
        )
        return

    # Цена уже есть — пересчитываем
    base = (order.item_price or 0) + (order.delivery_price or 0) + (order.commission or 0)
    discount = calculate_promo_discount(promo, base)

    order.promo_code = code
    order.discount_amount = discount
    order.total_price = max(0.0, base - discount - order.bonus_used)
    await session.flush()
    await use_promo(session, promo, order.id, db_user.id)
    await session.commit()
    await state.clear()

    promo_label = (
        f"{promo.discount_percent}%" if promo.discount_type == "percent"
        else f"{promo.discount_fixed:.2f} ₽"
    )
    await message.answer(
        f"✅ Промокод <code>{code}</code> применён!\n\n"
        f"Скидка: <b>{promo_label}</b> = <b>-{discount:.2f} ₽</b>\n"
        f"Итого к оплате: <b>{order.total_price:.2f} ₽</b>",
        parse_mode="HTML",
        reply_markup=pricing_response_keyboard(order.id),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# РАСЧЁТ СТОИМОСТИ — согласие / отказ клиента
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("pricing_agree:"))
async def pricing_agreed(callback: CallbackQuery, session: AsyncSession,
                         db_user: User, bot: Bot) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)
    if order is None or order.user_id != db_user.id:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return

    if order.bonus_used > 0:
        await spend_bonus(session, db_user, order.bonus_used, order_id=order.id)

    await update_order_status(session, order.id, OrderStatus.AWAITING_PAYMENT)
    await session.commit()

    payment_details = await get_payment_details(session)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await callback.message.answer(
        f"✅ <b>Отлично! Ожидаем оплату</b>\n\n{payment_details}\n\n"
        "📎 <b>После оплаты отправьте чек (фото или документ) в этот чат.</b>",
        parse_mode="HTML",
        reply_markup=receipt_keyboard(),
    )

    # Переводим пользователя в состояние ожидания чека
    from aiogram.fsm.context import FSMContext
    # Сохраняем order_id в state для получения чека
    # Используем user_id для получения state из bot
    from aiogram.fsm.storage.base import StorageKey
    from aiogram.fsm.storage.memory import MemoryStorage

    # Устанавливаем состояние ожидания чека напрямую через bot
    # Это делается через контекст — здесь недоступен, поэтому используем callback.message
    # Состояние будет установлено в следующем middleware-цикле
    # Вместо этого — сохраняем order_id в callback data и обрабатываем любой media

    for admin_id in config.admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"✅ <b>Клиент согласился с расчётом</b>\n\n"
                     f"Заказ: <b>{order.order_number}</b>\n"
                     f"👤 {db_user.mention}\n"
                     f"💰 Итого: <b>{order.total_price:.2f} ₽</b>\n"
                     f"Статус: 💳 Ожидает оплаты",
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.error("notify admin error: %s", exc)
    await callback.answer()


@router.callback_query(F.data.startswith("pricing_decline:"))
async def pricing_declined_start(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[1])
    await state.set_state(OrderFSM.entering_cancel_reason)
    await state.update_data(cancel_order_id=order_id)
    await callback.message.answer(
        "❌ <b>Укажите причину отказа:</b>", parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(OrderFSM.entering_cancel_reason, F.text)
async def pricing_declined_reason(message: Message, state: FSMContext,
                                  session: AsyncSession, db_user: User, bot: Bot) -> None:
    data = await state.get_data()
    order_id = data["cancel_order_id"]
    await state.clear()

    order = await set_order_cancel_reason(session, order_id, message.text)
    await session.commit()

    await message.answer(
        "❌ Заказ отменён. Если передумаете — создайте новый заказ.",
        reply_markup=main_menu_keyboard(),
    )

    from app.keyboards import order_admin_keyboard
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"❌ <b>Клиент отказался от заказа</b>\n\n"
                     f"Заказ: <b>{order.order_number}</b>\n"
                     f"👤 {db_user.mention}\n\n"
                     f"Причина: {message.text}",
                parse_mode="HTML",
                reply_markup=order_admin_keyboard(order.id, order.order_number),
            )
        except Exception as exc:
            logger.error("notify admin error: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# ОТПРАВКА ЧЕКА (фото, документ — из любого места пока заказ AWAITING_PAYMENT)
# ═══════════════════════════════════════════════════════════════════════════════

async def _forward_receipt_to_admins(
    bot: Bot, session: AsyncSession, db_user: User,
    file_id: str, file_type: str, order_id: int,
) -> None:
    """Пересылаем чек менеджерам."""
    from app.services import get_order_by_id as _get_order
    order = await _get_order(session, order_id)
    if not order:
        return

    caption = (
        f"🧾 <b>Чек об оплате</b>\n\n"
        f"📦 Заказ: <b>{order.order_number}</b>\n"
        f"👤 Клиент: {db_user.mention}\n"
        f"🆔 ID: <code>{db_user.telegram_id}</code>\n"
        f"💰 Сумма: <b>{order.total_price:.2f} ₽</b>"
    )

    from app.keyboards.client import receipt_admin_keyboard
    for admin_id in config.admin_ids:
        try:
            if file_type == "photo":
                await bot.send_photo(chat_id=admin_id, photo=file_id,
                                     caption=caption, parse_mode="HTML",
                                     reply_markup=receipt_admin_keyboard(order.id))
            elif file_type == "document":
                await bot.send_document(chat_id=admin_id, document=file_id,
                                        caption=caption, parse_mode="HTML",
                                        reply_markup=receipt_admin_keyboard(order.id))
        except Exception as exc:
            logger.error("forward receipt to admin %s: %s", admin_id, exc)


async def _handle_receipt(
    message: Message, session: AsyncSession, db_user: User, bot: Bot,
    file_id: str, file_type: str,
) -> None:
    """Общая логика получения чека."""
    from sqlalchemy import select
    from app.models import Order
    # Ищем активный заказ пользователя в статусе AWAITING_PAYMENT
    result = await session.execute(
        select(Order)
        .where(Order.user_id == db_user.id, Order.status == OrderStatus.AWAITING_PAYMENT)
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    order = result.scalar_one_or_none()
    if order is None:
        await message.answer(
            "⚠️ Не найдено заказа, ожидающего оплаты. "
            "Если вы ожидаете подтверждение — менеджер скоро свяжется.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await _forward_receipt_to_admins(bot, session, db_user, file_id, file_type, order.id)
    await message.answer(
        "✅ <b>Чек отправлен менеджеру на проверку.</b>\n\nОжидайте подтверждения оплаты.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.photo, ~F.via_bot)
async def handle_receipt_photo(message: Message, session: AsyncSession,
                               db_user: User, bot: Bot, state: FSMContext) -> None:
    """Фото от пользователя — может быть чеком."""
    current = await state.get_state()
    # Игнорируем если идёт FSM создания заказа
    if current in (
        OrderFSM.uploading_photos.state,
        OrderFSM.preview.state,
        OrderFSM.choosing_bonus.state,
    ):
        return
    # Проверяем есть ли заказ в ожидании оплаты
    from sqlalchemy import select
    from app.models import Order
    result = await session.execute(
        select(Order)
        .where(Order.user_id == db_user.id, Order.status == OrderStatus.AWAITING_PAYMENT)
        .limit(1)
    )
    if result.scalar_one_or_none() is None:
        return  # Нет заказа в ожидании — игнорируем фото
    await _handle_receipt(message, session, db_user, bot,
                          message.photo[-1].file_id, "photo")


@router.message(F.document, ~F.via_bot)
async def handle_receipt_document(message: Message, session: AsyncSession,
                                  db_user: User, bot: Bot, state: FSMContext) -> None:
    """Документ от пользователя — чек."""
    current = await state.get_state()
    if current in (OrderFSM.uploading_photos.state,):
        return
    from sqlalchemy import select
    from app.models import Order
    result = await session.execute(
        select(Order)
        .where(Order.user_id == db_user.id, Order.status == OrderStatus.AWAITING_PAYMENT)
        .limit(1)
    )
    if result.scalar_one_or_none() is None:
        return
    await _handle_receipt(message, session, db_user, bot,
                          message.document.file_id, "document")


# ═══════════════════════════════════════════════════════════════════════════════
# МЕНЕДЖЕР ПОДТВЕРЖДАЕТ / ОТКЛОНЯЕТ ОПЛАТУ
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("payment_confirm:"))
async def payment_confirmed(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)
    if order is None:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return

    await update_order_status(session, order.id, OrderStatus.PAID)
    await session.commit()

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("✅ Оплата подтверждена.", show_alert=True)

    try:
        await bot.send_message(
            chat_id=order.user.telegram_id,
            text=f"✅ <b>Оплата подтверждена!</b>\n\n"
                 f"📦 Заказ <b>{order.order_number}</b> переходит в обработку.\n"
                 "Мы уведомим вас о следующем статусе.",
            parse_mode="HTML",
        )
    except Exception as exc:
        logger.error("notify client payment confirm: %s", exc)


@router.callback_query(F.data.startswith("payment_reject:"))
async def payment_rejected(callback: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)
    if order is None:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer("❌ Чек отклонён.", show_alert=True)

    from app.services import get_payment_details
    payment_details = await get_payment_details(session)
    try:
        await bot.send_message(
            chat_id=order.user.telegram_id,
            text=f"❌ <b>Чек не прошёл проверку</b>\n\n"
                 f"📦 Заказ: <b>{order.order_number}</b>\n\n"
                 "Пожалуйста, проверьте реквизиты и отправьте новый чек.\n\n"
                 f"{payment_details}",
            parse_mode="HTML",
            reply_markup=receipt_keyboard(),
        )
    except Exception as exc:
        logger.error("notify client payment reject: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# ПОВТОР ЗАКАЗА
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("repeat_order:"))
async def repeat_order_confirm(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)
    if order is None or order.user_id != db_user.id:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return
    if order.status != OrderStatus.COMPLETED:
        await callback.answer("⚠️ Повторить можно только завершённый заказ.", show_alert=True)
        return
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"repeat_confirm:{order_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="repeat_cancel"),
    )
    await callback.message.answer(
        f"🔄 <b>Повторить заказ {order.order_number}?</b>\n\n"
        f"📝 {order.description[:200]}\n"
        f"🖼 Фото: {len(order.images)} шт.",
        parse_mode="HTML", reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("repeat_confirm:"))
async def repeat_order_create(callback: CallbackQuery, session: AsyncSession,
                              db_user: User, bot: Bot) -> None:
    source_id = int(callback.data.split(":")[1])
    source = await get_order_by_id(session, source_id)
    if source is None or source.user_id != db_user.id:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return
    new_order = await create_order(
        session=session, user_id=db_user.id,
        description=source.description,
        photo_file_ids=[img.file_id for img in source.images],
        found_price=source.found_price,
        desired_budget=source.desired_budget,
        source_order_id=source.id,
    )
    await session.commit()
    await callback.message.answer(
        f"✅ <b>Повторный заказ {new_order.order_number} создан!</b>",
        parse_mode="HTML", reply_markup=main_menu_keyboard(),
    )
    await notify_admins_new_order(bot, new_order)
    await notify_managers_new_order(bot, new_order, session)
    await callback.answer()


@router.callback_query(F.data == "repeat_cancel")
async def repeat_cancel(callback: CallbackQuery) -> None:
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Отменено.")
