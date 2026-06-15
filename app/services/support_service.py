from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import SupportTicket, TicketMessage, TicketStatus

logger = logging.getLogger(__name__)


async def _generate_ticket_number(session: AsyncSession) -> str:
    result = await session.execute(select(func.count()).select_from(SupportTicket))
    count = result.scalar_one() or 0
    return f"TKT-{(count + 1):06d}"


async def create_ticket(
    session: AsyncSession,
    user_id: int,
    subject: str,
    first_message: str,
) -> SupportTicket:
    ticket_number = await _generate_ticket_number(session)
    ticket = SupportTicket(
        ticket_number=ticket_number,
        user_id=user_id,
        subject=subject,
        status=TicketStatus.NEW,
    )
    session.add(ticket)
    await session.flush()
    session.add(TicketMessage(ticket_id=ticket.id, sender_role="client", text=first_message))
    await session.flush()
    await session.refresh(ticket)
    return ticket


async def get_ticket_by_id(session: AsyncSession, ticket_id: int) -> Optional[SupportTicket]:
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(selectinload(SupportTicket.messages), selectinload(SupportTicket.user))
    )
    return result.scalar_one_or_none()


async def get_tickets_by_user(session: AsyncSession, user_id: int) -> list[SupportTicket]:
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.user_id == user_id)
        .options(selectinload(SupportTicket.messages))
        .order_by(desc(SupportTicket.created_at))
    )
    return list(result.scalars().all())


async def get_all_tickets(
    session: AsyncSession,
    status_filter: Optional[TicketStatus] = None,
    limit: int = 30,
) -> list[SupportTicket]:
    q = (
        select(SupportTicket)
        .options(selectinload(SupportTicket.user), selectinload(SupportTicket.messages))
        .order_by(desc(SupportTicket.updated_at))
        .limit(limit)
    )
    if status_filter is not None:
        q = q.where(SupportTicket.status == status_filter)
    result = await session.execute(q)
    return list(result.scalars().all())


async def add_ticket_message(
    session: AsyncSession,
    ticket_id: int,
    text: str,
    sender_role: str,
) -> TicketMessage:
    msg = TicketMessage(ticket_id=ticket_id, sender_role=sender_role, text=text)
    session.add(msg)
    await session.flush()
    ticket = await session.get(SupportTicket, ticket_id)
    if ticket:
        ticket.updated_at = datetime.utcnow()
        if sender_role == "admin" and ticket.status == TicketStatus.NEW:
            ticket.status = TicketStatus.OPEN
    await session.flush()
    return msg


async def close_ticket(session: AsyncSession, ticket_id: int) -> Optional[SupportTicket]:
    ticket = await get_ticket_by_id(session, ticket_id)
    if ticket is None:
        return None
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = datetime.utcnow()
    await session.flush()
    return ticket


async def reopen_ticket(session: AsyncSession, ticket_id: int) -> Optional[SupportTicket]:
    ticket = await get_ticket_by_id(session, ticket_id)
    if ticket is None:
        return None
    ticket.status = TicketStatus.OPEN
    ticket.closed_at = None
    await session.flush()
    return ticket
