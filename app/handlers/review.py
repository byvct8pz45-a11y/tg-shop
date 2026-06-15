"""Отзывы: клиентский FSM + просмотр."""
from __future__ import annotations
import logging
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
from app.keyboards import (
    cancel_keyboard, main_menu_keyboard, review_action_keyboard,
    rating_keyboard, review_photo_keyboard, review_confirm_keyboard,
)
from app.models import OrderStatus, User
from app.services import (
    create_review, get_published_reviews, get_order_by_id,
    get_user_review_for_order, approve_review, reject_review,
    issue_first_order_promo,
)
from app.states import ReviewFSM
from config import config

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "⭐ Отзывы")
async def show_reviews(message: Message, session: AsyncSession) -> None:
    reviews = await get_published_reviews(session, limit=10)
    if not reviews:
        await message.answer("⭐ <b>Отзывы</b>\n\nПока отзывов нет. Будьте первым!",
                             parse_mode="HTML", reply_markup=main_menu_keyboard())
        return
    lines = ["⭐ <b>Отзывы наших клиентов</b>\n"]
    for rv in reviews:
        stars = "⭐" * rv.rating
        date_str = rv.created_at.strftime("%d.%m.%Y")
        name = f"@{rv.username}" if rv.username else f"Пользователь {rv.telegram_id}"
        lines.append(f"{stars} <b>{name}</b>  <i>{date_str}</i>\n{rv.text}\n")
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_menu_keyboard())


# ─── FSM написания отзыва ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("leave_review:"))
async def leave_review_start(callback: CallbackQuery, state: FSMContext,
                              session: AsyncSession, db_user: User) -> None:
    order_id = int(callback.data.split(":")[1])
    order = await get_order_by_id(session, order_id)
    if order is None or order.user_id != db_user.id:
        await callback.answer("⚠️ Заказ не найден.", show_alert=True)
        return
    if order.status != OrderStatus.COMPLETED:
        await callback.answer("⚠️ Отзыв только для завершённых заказов.", show_alert=True)
        return
    existing = await get_user_review_for_order(session, db_user.id, order_id)
    if existing:
        await callback.answer("Вы уже оставили отзыв по этому заказу.", show_alert=True)
        return
    await state.set_state(ReviewFSM.choosing_rating)
    await state.update_data(review_order_id=order_id)
    await callback.message.answer(
        f"⭐ <b>Оценка сервиса</b>\n\nЗаказ: <b>{order.order_number}</b>\n\nВыберите оценку от 1 до 5:",
        parse_mode="HTML", reply_markup=rating_keyboard(),
    )
    await callback.answer()


@router.callback_query(ReviewFSM.choosing_rating, F.data.startswith("rating:"))
async def review_rating_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    rating = int(callback.data.split(":")[1])
    await state.update_data(review_rating=rating)
    await state.set_state(ReviewFSM.entering_text)
    stars = "⭐" * rating
    await callback.message.answer(
        f"Оценка: {stars}\n\n✏️ Напишите текст отзыва:",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(ReviewFSM.entering_text, F.text == "❌ Отмена")
async def cancel_review(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_menu_keyboard())


@router.message(ReviewFSM.entering_text, F.text)
async def review_text_entered(message: Message, state: FSMContext) -> None:
    await state.update_data(review_text=message.text)
    await state.set_state(ReviewFSM.uploading_photo)
    await message.answer("📷 Прикрепите фото (необязательно) или нажмите <b>⏭ Пропустить фото</b>:",
                         parse_mode="HTML", reply_markup=review_photo_keyboard())


@router.message(ReviewFSM.uploading_photo, F.photo)
async def review_photo_uploaded(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await state.update_data(review_photo=file_id)
    await state.set_state(ReviewFSM.confirming)
    await _show_review_preview(message, state)


@router.message(ReviewFSM.uploading_photo, F.text == "⏭ Пропустить фото")
async def review_skip_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(review_photo=None)
    await state.set_state(ReviewFSM.confirming)
    await _show_review_preview(message, state)


@router.message(ReviewFSM.uploading_photo, F.text == "❌ Отмена")
async def cancel_review_photo(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_menu_keyboard())


async def _show_review_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    rating = data.get("review_rating", 5)
    stars = "⭐" * rating
    text = data.get("review_text", "")
    has_photo = bool(data.get("review_photo"))
    preview = (
        f"👁 <b>Предпросмотр отзыва</b>\n\n"
        f"Оценка: {stars}\n"
        f"Текст: {text}\n"
        f"Фото: {'✅ прикреплено' if has_photo else '—'}\n\n"
        "Отправить отзыв на модерацию?"
    )
    if data.get("review_photo"):
        await message.answer_photo(photo=data["review_photo"], caption=preview,
                                   parse_mode="HTML", reply_markup=review_confirm_keyboard())
    else:
        await message.answer(preview, parse_mode="HTML", reply_markup=review_confirm_keyboard())


@router.callback_query(ReviewFSM.confirming, F.data == "review_confirm:yes")
async def submit_review(callback: CallbackQuery, state: FSMContext,
                        session: AsyncSession, db_user: User, bot: Bot) -> None:
    # Отвечаем на callback немедленно, чтобы не получить timeout
    await callback.answer()
    data = await state.get_data()
    await state.clear()
    review = await create_review(
        session=session, user=db_user,
        order_id=data["review_order_id"],
        rating=data["review_rating"],
        text=data["review_text"],
        photo_file_id=data.get("review_photo"),
    )
    await session.commit()

    # Убираем inline-кнопки с сообщения-превью
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Отправляем подтверждение с reply-клавиатурой главного меню
    await bot.send_message(
        chat_id=callback.from_user.id,
        text="✅ <b>Спасибо за отзыв!</b>\n\nОн отправлен на модерацию и появится после одобрения.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    # Уведомляем администраторов
    from app.keyboards.admin import review_admin_keyboard
    stars = "⭐" * review.rating
    admin_text = (
        f"⭐ <b>Новый отзыв на модерацию</b>\n\n"
        f"👤 {db_user.mention}\n"
        f"Оценка: {stars}\n\n"
        f"{review.text}"
    )
    for admin_id in config.admin_ids:
        try:
            if review.photo_file_id:
                await bot.send_photo(chat_id=admin_id, photo=review.photo_file_id,
                                     caption=admin_text, parse_mode="HTML",
                                     reply_markup=review_admin_keyboard(review.id, "PENDING"))
            else:
                await bot.send_message(chat_id=admin_id, text=admin_text, parse_mode="HTML",
                                       reply_markup=review_admin_keyboard(review.id, "PENDING"))
        except Exception as exc:
            logger.error("notify admin %s: %s", admin_id, exc)


@router.callback_query(ReviewFSM.confirming, F.data == "review_confirm:no")
async def cancel_review_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await callback.answer()
    await state.clear()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await bot.send_message(
        chat_id=callback.from_user.id,
        text="Отменено.",
        reply_markup=main_menu_keyboard(),
    )
