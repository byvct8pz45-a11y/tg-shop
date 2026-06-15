"""Все модели базы данных."""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─── Перечисления ─────────────────────────────────────────────────────────────

class OrderStatus(str, enum.Enum):
    NEW = "Новый"
    CALCULATING = "Расчёт стоимости"
    AWAITING_APPROVAL = "Ожидает согласования"
    AWAITING_PAYMENT = "Ожидает оплаты"
    PAID = "Оплачен"
    PURCHASED = "Выкуплен"
    IN_TRANSIT = "В пути"
    RECEIVED = "Получен"
    COMPLETED = "Завершён"
    CANCELLED = "Отменён"


class TicketStatus(str, enum.Enum):
    NEW = "Новый"
    OPEN = "Открытый"
    CLOSED = "Закрытый"


class ReviewStatus(str, enum.Enum):
    PENDING = "На модерации"
    APPROVED = "Одобрен"
    REJECTED = "Отклонён"


class ManagerRole(str, enum.Enum):
    ADMIN = "Администратор"
    MANAGER = "Менеджер"


class BonusOperationType(str, enum.Enum):
    REFERRAL_REWARD = "Реферальное вознаграждение"
    REFERRAL_DISCOUNT = "Скидка реферала"
    PROMO_DISCOUNT = "Скидка по промокоду"
    BONUS_USED = "Использование бонуса"
    MANUAL = "Ручное начисление"


class FavoriteCategory(str, enum.Enum):
    CLOTHES = "Одежда"
    SHOES = "Обувь"
    ELECTRONICS = "Электроника"
    HOME = "Для дома"
    ACCESSORIES = "Аксессуары"
    OTHER = "Без категории"


# ─── Пользователи ─────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Реферальная система
    referrer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    referral_discount_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Промокод за первый заказ
    first_order_promo_issued: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Бонусный баланс
    bonus_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bonus_total_earned: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bonus_total_spent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Связи
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="user", foreign_keys="Order.user_id", lazy="selectin")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="user", lazy="selectin")
    reviews: Mapped[List["Review"]] = relationship("Review", back_populates="user", lazy="selectin")
    tickets: Mapped[List["SupportTicket"]] = relationship("SupportTicket", back_populates="user", lazy="selectin")
    referrals: Mapped[List["User"]] = relationship("User", foreign_keys=[referrer_id], lazy="noload")
    promos: Mapped[List["Promo"]] = relationship("Promo", back_populates="user", foreign_keys="Promo.user_id", lazy="selectin")
    bonus_history: Mapped[List["BonusTransaction"]] = relationship("BonusTransaction", back_populates="user", lazy="selectin")
    favorites: Mapped[List["Favorite"]] = relationship("Favorite", back_populates="user", lazy="selectin")

    @property
    def full_name(self) -> str:
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    @property
    def mention(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.full_name

    @property
    def referral_count(self) -> int:
        return len(self.referrals)


# ─── Менеджеры ────────────────────────────────────────────────────────────────

class Manager(Base):
    __tablename__ = "managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[ManagerRole] = mapped_column(Enum(ManagerRole), default=ManagerRole.MANAGER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    added_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    orders: Mapped[List["Order"]] = relationship("Order", back_populates="manager", lazy="selectin")

    @property
    def mention(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.first_name


# ─── Заказы ───────────────────────────────────────────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    manager_id: Mapped[Optional[int]] = mapped_column(ForeignKey("managers.id"), nullable=True)

    description: Mapped[str] = mapped_column(Text, nullable=False)
    found_price: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    desired_budget: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    # Расчёт стоимости
    item_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delivery_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    commission: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Скидки и бонусы
    promo_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bonus_used: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Отказ
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.NEW, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Повтор заказа
    source_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id"), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="orders", foreign_keys=[user_id])
    manager: Mapped[Optional["Manager"]] = relationship("Manager", back_populates="orders")
    images: Mapped[List["OrderImage"]] = relationship("OrderImage", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    messages: Mapped[List["Message"]] = relationship("Message", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    review: Mapped[Optional["Review"]] = relationship("Review", back_populates="order", uselist=False, lazy="selectin")
    source_order: Mapped[Optional["Order"]] = relationship("Order", remote_side="Order.id", foreign_keys=[source_order_id])


class OrderImage(Base):
    __tablename__ = "order_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    file_id: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="images")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    sender_role: Mapped[str] = mapped_column(String(16), nullable=False)  # "client" | "admin"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="messages")
    user: Mapped[Optional["User"]] = relationship("User", back_populates="messages")


# ─── Настройки ────────────────────────────────────────────────────────────────

class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


# ─── Отзывы ───────────────────────────────────────────────────────────────────

class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    text: Mapped[str] = mapped_column(Text, nullable=False)
    photo_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="reviews")
    order: Mapped["Order"] = relationship("Order", back_populates="review")


# ─── Поддержка ────────────────────────────────────────────────────────────────

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_number: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.NEW, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="tickets")
    messages: Mapped[List["TicketMessage"]] = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan", lazy="selectin")


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id"), nullable=False)
    sender_role: Mapped[str] = mapped_column(String(16), nullable=False)  # "client" | "admin"
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    ticket: Mapped["SupportTicket"] = relationship("SupportTicket", back_populates="messages")


# ─── Промокоды ────────────────────────────────────────────────────────────────

class Promo(Base):
    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    # Тип скидки: "percent" или "fixed"
    discount_type: Mapped[str] = mapped_column(String(16), nullable=False, default="percent")
    discount_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    discount_fixed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Привязка к пользователю (только для автоматических промокодов за первый заказ)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_in_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    # Кто использовал (для глобальных промокодов)
    used_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)  # telegram_id создателя

    user: Mapped[Optional["User"]] = relationship("User", back_populates="promos", foreign_keys=[user_id])


# ─── Бонусные транзакции ──────────────────────────────────────────────────────

class BonusTransaction(Base):
    __tablename__ = "bonus_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    operation_type: Mapped[BonusOperationType] = mapped_column(Enum(BonusOperationType), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="bonus_history")


# ─── Избранное ────────────────────────────────────────────────────────────────

class Favorite(Base):
    __tablename__ = "favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    post_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    category: Mapped[FavoriteCategory] = mapped_column(Enum(FavoriteCategory), default=FavoriteCategory.OTHER, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="favorites")
