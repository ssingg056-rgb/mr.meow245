import os
import motor.motor_asyncio
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid
from pymongo.server_api import ServerApi


MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://ssingg056_db_user:ssingg056_db_user@cluster0.ivjhdbz.mongodb.net/?appName=Cluster0"
)
DB_NAME = "mr_meow"


class Database:
    def __init__(self):
        self.client: motor.motor_asyncio.AsyncIOMotorClient | None = None
        self.db: motor.motor_asyncio.AsyncIOMotorDatabase | None = None

    async def connect(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(
            MONGO_URI,
            server_api=ServerApi("1"),
            maxPoolSize=10,
            retryWrites=True,
        )
        self.db = self.client[DB_NAME]
        await self._create_indexes()

    async def _create_indexes(self):
        # conversations: unique compound + TTL on updated_at (30 days)
        await self.db.conversations.create_index(
            [("guild_id", ASCENDING), ("channel_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True,
        )
        await self.db.conversations.create_index(
            "updated_at",
            expireAfterSeconds=2592000,
        )

        # economy_users: unique compound (guild_id, user_id)
        await self.db.economy_users.create_index(
            [("guild_id", ASCENDING), ("user_id", ASCENDING)],
            unique=True,
        )

        # economy_transactions: compound for queries
        await self.db.economy_transactions.create_index(
            [("guild_id", ASCENDING), ("timestamp", DESCENDING)]
        )

        # capped collection for transactions (auto-evicts old docs)
        try:
            await self.db.create_collection(
                "economy_transactions",
                capped=True,
                size=100_000_000,
                max=500_000,
            )
        except CollectionInvalid:
            pass

        # shop_items: unique compound (guild_id, name)
        await self.db.shop_items.create_index(
            [("guild_id", ASCENDING), ("name", ASCENDING)],
            unique=True,
        )

        # guild_configs: _id = guild_id (natural key)
        await self.db.guild_configs.create_index("_id", unique=True)

    def get_collection(self, name: str):
        if self.db is None:
            raise RuntimeError("Database not connected")
        return self.db[name]

    async def close(self):
        if self.client:
            self.client.close()


database = Database()