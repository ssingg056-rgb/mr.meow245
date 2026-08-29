from datetime import datetime
from typing import Optional
import motor.motor_asyncio
from pymongo import ReturnDocument
from pymongo.errors import CollectionInvalid


MAX_HISTORY = 20


class HistoryManager:
    def __init__(self, db: motor.motor_asyncio.AsyncIOMotorDatabase):
        self.conversations = db.conversations

    async def get_history(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        limit: int = MAX_HISTORY,
    ) -> list[dict[str, str]]:
        doc = await self.conversations.find_one(
            {"guild_id": guild_id, "channel_id": channel_id, "user_id": user_id},
            projection={"messages": 1},
        )
        if not doc:
            return []
        messages = doc.get("messages", [])
        return messages[-limit:]

    async def append_message(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        role: str,
        content: str,
    ) -> None:
        now = datetime.utcnow()
        message = {"role": role, "content": content, "timestamp": now}

        await self.conversations.find_one_and_update(
            {"guild_id": guild_id, "channel_id": channel_id, "user_id": user_id},
            {
                "$push": {
                    "messages": {
                        "$each": [message],
                        "$slice": -MAX_HISTORY,
                    }
                },
                "$set": {"updated_at": now},
                "$setOnInsert": {
                    "guild_id": guild_id,
                    "channel_id": channel_id,
                    "user_id": user_id,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    async def clear_history(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
    ) -> bool:
        result = await self.conversations.delete_one(
            {"guild_id": guild_id, "channel_id": channel_id, "user_id": user_id}
        )
        return result.deleted_count > 0

    async def get_all_user_conversations(self, guild_id: int, user_id: int) -> list[dict]:
        cursor = self.conversations.find(
            {"guild_id": guild_id, "user_id": user_id},
            projection={"channel_id": 1, "updated_at": 1, "messages": {"$slice": 1}},
        )
        return await cursor.to_list(length=50)