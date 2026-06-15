from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    admin_ids: list[int]
    database_url: str
    log_level: str
    reviews_channel_id: int  # канал для публикации отзывов (0 = отключено)
    favorites_channel_id: int  # канал с находками (для избранного)

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("BOT_TOKEN", "")
        if not token:
            raise ValueError("BOT_TOKEN is not set")

        admin_ids: list[int] = []
        for part in os.getenv("ADMIN_IDS", "").split(","):
            part = part.strip()
            if part.isdigit():
                admin_ids.append(int(part))

        reviews_channel_raw = os.getenv("REVIEWS_CHANNEL_ID", "0")
        favorites_channel_raw = os.getenv("FAVORITES_CHANNEL_ID", "0")

        return cls(
            bot_token=token,
            admin_ids=admin_ids,
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            reviews_channel_id=int(reviews_channel_raw) if reviews_channel_raw.lstrip("-").isdigit() else 0,
            favorites_channel_id=int(favorites_channel_raw) if favorites_channel_raw.lstrip("-").isdigit() else 0,
        )


config = Config.from_env()
