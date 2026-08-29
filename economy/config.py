from datetime import datetime
from typing import Optional
import motor.motor_asyncio
from pymongo import ReturnDocument

from models import GuildConfig


DEFAULT_CONFIG = {
    "economy_enabled": True,
    "currency_name": "Meow Coins",
    "currency_symbol": "🐱",
    "daily_amount": 100,
    "weekly_amount": 500,
    "msg_reward_min": 5,
    "msg_reward_max": 15,
    "msg_cooldown_seconds": 60,
    "msg_reward_enabled": True,
}


class EconomyConfig:
    def __init__(self, db: motor.motor_asyncio.AsyncIOMotorDatabase):
        self.collection = db.guild_configs

    async def get_config(self, guild_id: int) -> GuildConfig:
        config = await self.collection.find_one({"_id": guild_id})
        if not config:
            config = await self.create_default_config(guild_id)
        return config

    async def create_default_config(self, guild_id: int) -> GuildConfig:
        now = datetime.utcnow()
        config = {
            "_id": guild_id,
            **DEFAULT_CONFIG,
            "created_at": now,
            "updated_at": now,
        }
        await self.collection.insert_one(config)
        return config

    async def update_config(self, guild_id: int, updates: dict) -> GuildConfig:
        now = datetime.utcnow()
        updates["updated_at"] = now
        config = await self.collection.find_one_and_update(
            {"_id": guild_id},
            {"$set": updates},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return config

    async def is_economy_enabled(self, guild_id: int) -> bool:
        config = await self.get_config(guild_id)
        return config.get("economy_enabled", True)

    async def get_currency_info(self, guild_id: int) -> tuple[str, str]:
        config = await self.get_config(guild_id)
        return config.get("currency_name", "Meow Coins"), config.get("currency_symbol", "🐱")

    async def get_daily_amount(self, guild_id: int) -> int:
        config = await self.get_config(guild_id)
        return config.get("daily_amount", 100)

    async def get_weekly_amount(self, guild_id: int) -> int:
        config = await self.get_config(guild_id)
        return config.get("weekly_amount", 500)

    async def get_msg_reward_range(self, guild_id: int) -> tuple[int, int]:
        config = await self.get_config(guild_id)
        return config.get("msg_reward_min", 5), config.get("msg_reward_max", 15)

    async def get_msg_cooldown(self, guild_id: int) -> int:
        config = await self.get_config(guild_id)
        return config.get("msg_cooldown_seconds", 60)

    async def is_msg_reward_enabled(self, guild_id: int) -> bool:
        config = await self.get_config(guild_id)
        return config.get("msg_reward_enabled", True)

    VALID_SETTINGS = {
        "enabled": ("economy_enabled", bool),
        "currency_name": ("currency_name", str),
        "currency_symbol": ("currency_symbol", str),
        "daily": ("daily_amount", int),
        "weekly": ("weekly_amount", int),
        "msg_reward_min": ("msg_reward_min", int),
        "msg_reward_max": ("msg_reward_max", int),
        "msg_cooldown": ("msg_cooldown_seconds", int),
        "msg_reward_enabled": ("msg_reward_enabled", bool),
    }

    async def set_setting(self, guild_id: int, setting: str, value: str) -> tuple[bool, str]:
        if setting not in self.VALID_SETTINGS:
            return False, f"Invalid setting. Valid: {', '.join(self.VALID_SETTINGS.keys())}"

        field_name, field_type = self.VALID_SETTINGS[setting]

        try:
            if field_type == bool:
                parsed_value = value.lower() in ("true", "1", "yes", "on", "enable")
            elif field_type == int:
                parsed_value = int(value)
            else:
                parsed_value = value
        except ValueError:
            return False, f"Invalid value for {setting}. Expected {field_type.__name__}."

        if field_name in ("msg_reward_min", "msg_reward_max"):
            config = await self.get_config(guild_id)
            min_val = config.get("msg_reward_min", 5)
            max_val = config.get("msg_reward_max", 15)
            if field_name == "msg_reward_min":
                if parsed_value > max_val:
                    return False, "min cannot exceed max"
            else:
                if parsed_value < min_val:
                    return False, "max cannot be less than min"

        await self.update_config(guild_id, {field_name: parsed_value})
        return True, f"Set {setting} to {parsed_value}"