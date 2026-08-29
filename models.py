from datetime import datetime
from typing import TypedDict, Literal, Optional


class GuildConfig(TypedDict):
    _id: int
    economy_enabled: bool
    currency_name: str
    currency_symbol: str
    daily_amount: int
    weekly_amount: int
    msg_reward_min: int
    msg_reward_max: int
    msg_cooldown_seconds: int
    msg_reward_enabled: bool
    created_at: datetime
    updated_at: datetime


class EconomyUser(TypedDict):
    _id: str
    guild_id: int
    user_id: int
    balance: int
    total_earned: int
    last_daily: Optional[datetime]
    last_weekly: Optional[datetime]
    last_msg_reward: Optional[datetime]
    created_at: datetime


class Transaction(TypedDict):
    _id: str
    guild_id: int
    from_user: Optional[int]
    to_user: Optional[int]
    amount: int
    type: Literal[
        "daily",
        "weekly",
        "message",
        "transfer",
        "gamble_win",
        "gamble_loss",
        "shop_purchase",
        "admin_give",
        "admin_take",
    ]
    timestamp: datetime
    note: Optional[str]


class ShopItem(TypedDict):
    _id: str
    guild_id: int
    name: str
    price: int
    description: str
    role_id: Optional[int]
    stock: Optional[int]
    created_at: datetime


class ConversationDoc(TypedDict):
    _id: str
    guild_id: int
    channel_id: int
    user_id: int
    messages: list[dict[str, str]]
    updated_at: datetime


TransactionType = Literal[
    "daily",
    "weekly",
    "message",
    "transfer",
    "gamble_win",
    "gamble_loss",
    "shop_purchase",
    "admin_give",
    "admin_take",
]