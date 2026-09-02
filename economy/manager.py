import random
from datetime import datetime, timedelta
from typing import Optional
import motor.motor_asyncio
from pymongo import ReturnDocument, ASCENDING, DESCENDING

from models import EconomyUser, Transaction, ShopItem, TransactionType
from economy.config import EconomyConfig


class EconomyManager:
    def __init__(self, db: motor.motor_asyncio.AsyncIOMotorDatabase, config: EconomyConfig):
        self.db = db
        self.config = config
        self.users = db.economy_users
        self.transactions = db.economy_transactions
        self.shop_items = db.shop_items

    async def _ensure_user(self, guild_id: int, user_id: int) -> EconomyUser:
        user = await self.users.find_one({"guild_id": guild_id, "user_id": user_id})
        if not user:
            now = datetime.utcnow()
            user = {
                "guild_id": guild_id,
                "user_id": user_id,
                "balance": 0,
                "total_earned": 0,
                "last_daily": None,
                "last_weekly": None,
                "last_msg_reward": None,
                "created_at": now,
            }
            await self.users.insert_one(user)
        return user

    async def get_balance(self, guild_id: int, user_id: int) -> int:
        user = await self._ensure_user(guild_id, user_id)
        return user.get("balance", 0)

    async def add_balance(self, guild_id: int, user_id: int, amount: int) -> int:
        result = await self.users.find_one_and_update(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"balance": amount, "total_earned": max(0, amount)}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return result.get("balance", 0)

    async def remove_balance(self, guild_id: int, user_id: int, amount: int) -> int:
        result = await self.users.find_one_and_update(
            {"guild_id": guild_id, "user_id": user_id},
            {"$inc": {"balance": -amount}},
            return_document=ReturnDocument.AFTER,
        )
        return result.get("balance", 0) if result else 0

    async def transfer(
        self,
        guild_id: int,
        from_id: int,
        to_id: int,
        amount: int,
    ) -> tuple[bool, str]:
        if from_id == to_id:
            return False, "Cannot transfer to yourself"

        if amount <= 0:
            return False, "Amount must be positive"

        from_user = await self._ensure_user(guild_id, from_id)
        if from_user.get("balance", 0) < amount:
            return False, "Insufficient balance"

        await self._ensure_user(guild_id, to_id)

        async with await self.db.client.start_session() as session:
            async with session.start_transaction():
                await self.users.update_one(
                    {"guild_id": guild_id, "user_id": from_id},
                    {"$inc": {"balance": -amount}},
                    session=session,
                )
                await self.users.update_one(
                    {"guild_id": guild_id, "user_id": to_id},
                    {"$inc": {"balance": amount}},
                    session=session,
                )
                await self.transactions.insert_one(
                    {
                        "guild_id": guild_id,
                        "from_user": from_id,
                        "to_user": to_id,
                        "amount": amount,
                        "type": "transfer",
                        "timestamp": datetime.utcnow(),
                        "note": f"Transfer from {from_id} to {to_id}",
                    },
                    session=session,
                )

        return True, f"Transferred {amount} to user {to_id}"

    async def claim_daily(self, guild_id: int, user_id: int) -> tuple[bool, str, int]:
        await self._ensure_user(guild_id, user_id)
        now = datetime.utcnow()
        daily_amount = await self.config.get_daily_amount(guild_id)

        user = await self.users.find_one({"guild_id": guild_id, "user_id": user_id})
        last_daily = user.get("last_daily")

        if last_daily and now - last_daily < timedelta(days=1):
            next_claim = last_daily + timedelta(days=1)
            remaining = next_claim - now
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            return False, f"Daily already claimed. Next claim in {hours}h {minutes}m", 0

        new_balance = await self.add_balance(guild_id, user_id, daily_amount)
        await self.users.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"last_daily": now}},
        )
        await self._log_transaction(guild_id, None, user_id, daily_amount, "daily", f"Daily reward")
        return True, f"Claimed daily reward of {daily_amount}", new_balance

    async def claim_weekly(self, guild_id: int, user_id: int) -> tuple[bool, str, int]:
        await self._ensure_user(guild_id, user_id)
        now = datetime.utcnow()
        weekly_amount = await self.config.get_weekly_amount(guild_id)

        user = await self.users.find_one({"guild_id": guild_id, "user_id": user_id})
        last_weekly = user.get("last_weekly")

        if last_weekly and now - last_weekly < timedelta(weeks=1):
            next_claim = last_weekly + timedelta(weeks=1)
            remaining = next_claim - now
            days = remaining.days
            hours = int(remaining.seconds // 3600)
            return False, f"Weekly already claimed. Next claim in {days}d {hours}h", 0

        new_balance = await self.add_balance(guild_id, user_id, weekly_amount)
        await self.users.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"last_weekly": now}},
        )
        await self._log_transaction(guild_id, None, user_id, weekly_amount, "weekly", f"Weekly reward")
        return True, f"Claimed weekly reward of {weekly_amount}", new_balance

    async def message_reward(self, guild_id: int, user_id: int) -> Optional[int]:
        if not await self.config.is_msg_reward_enabled(guild_id):
            return None

        await self._ensure_user(guild_id, user_id)
        now = datetime.utcnow()
        min_amt, max_amt = await self.config.get_msg_reward_range(guild_id)
        cooldown = await self.config.get_msg_cooldown(guild_id)

        user = await self.users.find_one({"guild_id": guild_id, "user_id": user_id})
        last_reward = user.get("last_msg_reward")

        if last_reward and now - last_reward < timedelta(seconds=cooldown):
            return None

        amount = random.randint(min_amt, max_amt)
        await self.add_balance(guild_id, user_id, amount)
        await self.users.update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {"$set": {"last_msg_reward": now}},
        )
        await self._log_transaction(guild_id, None, user_id, amount, "message", f"Message reward")
        return amount

    async def gamble(self, guild_id: int, user_id: int, amount: int) -> tuple[bool, str, int]:
        await self._ensure_user(guild_id, user_id)

        if amount <= 0:
            return False, "Amount must be positive", 0

        user = await self.users.find_one({"guild_id": guild_id, "user_id": user_id})
        balance = user.get("balance", 0)

        if balance < amount:
            return False, "Insufficient balance", balance

        won = random.random() < 0.5
        now = datetime.utcnow()

        if won:
            new_balance = await self.add_balance(guild_id, user_id, amount)
            await self._log_transaction(guild_id, None, user_id, amount, "gamble_win", f"Won gamble")
            return True, f"🎉 You won {amount}!", new_balance
        else:
            new_balance = await self.remove_balance(guild_id, user_id, amount)
            await self._log_transaction(guild_id, None, user_id, amount, "gamble_loss", f"Lost gamble")
            return False, f"💸 You lost {amount}. Better luck next time!", new_balance

    async def get_leaderboard(self, guild_id: int, page: int = 1) -> list[dict]:
        skip = (page - 1) * 10
        cursor = self.users.find({"guild_id": guild_id}).sort("balance", DESCENDING).skip(skip).limit(10)
        return await cursor.to_list(length=10)

    async def get_shop(self, guild_id: int) -> list[ShopItem]:
        cursor = self.shop_items.find({"guild_id": guild_id}).sort("name", ASCENDING)
        return await cursor.to_list(length=50)

    async def get_shop_item(self, guild_id: int, name: str) -> Optional[ShopItem]:
        return await self.shop_items.find_one({"guild_id": guild_id, "name": name.lower()})

    async def buy_item(
        self,
        guild_id: int,
        user_id: int,
        item_name: str,
        quantity: int = 1,
        bot_member=None,
        user_member=None,
    ) -> tuple[bool, str]:
        item = await self.get_shop_item(guild_id, item_name)
        if not item:
            return False, "Item not found in shop"

        if item.get("stock") is not None and item["stock"] < quantity:
            return False, f"Not enough stock. Only {item['stock']} left"

        total_price = item["price"] * quantity
        user = await self._ensure_user(guild_id, user_id)
        if user.get("balance", 0) < total_price:
            return False, f"Insufficient balance. Need {total_price}"

        await self.remove_balance(guild_id, user_id, total_price)

        if item.get("stock") is not None:
            await self.shop_items.update_one(
                {"_id": item["_id"]},
                {"$inc": {"stock": -quantity}},
            )

        role_id = item.get("role_id")
        if role_id and bot_member and user_member:
            try:
                role = bot_member.guild.get_role(role_id)
                if role and role < bot_member.top_role:
                    await user_member.add_roles(role, reason=f"Purchased {item['name']}")
            except Exception:
                pass

        await self._log_transaction(
            guild_id, None, user_id, total_price, "shop_purchase", f"Bought {quantity}x {item['name']}"
        )

        return True, f"Purchased {quantity}x {item['name']} for {total_price}"

    async def add_shop_item(
        self,
        guild_id: int,
        name: str,
        price: int,
        description: str,
        role_id: Optional[int] = None,
        stock: Optional[int] = None,
    ) -> tuple[bool, str]:
        if price < 0:
            return False, "Price cannot be negative"

        existing = await self.get_shop_item(guild_id, name)
        if existing:
            return False, "Item already exists"

        item = {
            "guild_id": guild_id,
            "name": name.lower(),
            "price": price,
            "description": description,
            "role_id": role_id,
            "stock": stock,
            "created_at": datetime.utcnow(),
        }
        await self.shop_items.insert_one(item)
        return True, f"Added {name} to shop for {price}"

    async def remove_shop_item(self, guild_id: int, name: str) -> tuple[bool, str]:
        result = await self.shop_items.delete_one({"guild_id": guild_id, "name": name.lower()})
        if result.deleted_count == 0:
            return False, "Item not found"
        return True, f"Removed {name} from shop"

    async def admin_give(self, guild_id: int, user_id: int, amount: int) -> tuple[bool, str, int]:
        await self._ensure_user(guild_id, user_id)
        new_balance = await self.add_balance(guild_id, user_id, amount)
        await self._log_transaction(guild_id, None, user_id, amount, "admin_give", f"Admin give")
        return True, f"Gave {amount} to user {user_id}", new_balance

    async def admin_take(self, guild_id: int, user_id: int, amount: int) -> tuple[bool, str, int]:
        await self._ensure_user(guild_id, user_id)
        user = await self.users.find_one({"guild_id": guild_id, "user_id": user_id})
        if user.get("balance", 0) < amount:
            return False, "User has insufficient balance", user.get("balance", 0)
        new_balance = await self.remove_balance(guild_id, user_id, amount)
        await self._log_transaction(guild_id, None, user_id, amount, "admin_take", f"Admin take")
        return True, f"Took {amount} from user {user_id}", new_balance

    async def _perform_activity(self, guild_id: int, user_id: int, activity: str, reward_min: int, reward_max: int, cooldown_seconds: int, txn_type: str) -> tuple[bool, str, Optional[int]]:
        """
        Generic helper for activity commands like fish, hunt, mine.
        Returns (success, message, new_balance) where new_balance is None if on cooldown.
        """
        # Ensure user exists
        await self._ensure_user(guild_id, user_id)
        now = datetime.utcnow()
        field_name = f"last_{activity}"
        user = await self.users.find_one({"guild_id": guild_id, "user_id": user_id})
        last_time = user.get(field_name)
        if last_time and now - last_time < timedelta(seconds=cooldown_seconds):
            next_time = last_time + timedelta(seconds=cooldown_seconds)
            remaining = next_time - now
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            return False, f"{activity.title()} is on cooldown. Try again in {minutes}m {seconds}s.", None
        amount = random.randint(reward_min, reward_max)
        result = await self.users.find_one_and_update(
            {"guild_id": guild_id, "user_id": user_id},
            {
                "$inc": {"balance": amount, "total_earned": max(0, amount)},
                "$set": {field_name: now},
            },
            return_document=ReturnDocument.AFTER,
        )
        new_balance = result.get("balance", 0) if result else 0
        await self._log_transaction(guild_id, None, user_id, amount, txn_type, f"{activity.title()} reward")
        return True, f"You {activity}ed and earned {amount}!", new_balance

    async def fish(self, guild_id: int, user_id: int) -> tuple[bool, str, Optional[int]]:
        # Fish reward: 15-50 coins, 30 min cooldown
        return await self._perform_activity(guild_id, user_id, "fish", 15, 50, 30 * 60, "fish_reward")

    async def hunt(self, guild_id: int, user_id: int) -> tuple[bool, str, Optional[int]]:
        # Hunt reward: 25-75 coins, 45 min cooldown
        return await self._perform_activity(guild_id, user_id, "hunt", 25, 75, 45 * 60, "hunt_reward")

    async def mine(self, guild_id: int, user_id: int) -> tuple[bool, str, Optional[int]]:
        # Mine reward: 30-100 coins, 60 min cooldown
        return await self._perform_activity(guild_id, user_id, "mine", 30, 100, 60 * 60, "mine_reward")

    async def _log_transaction(
        self,
        guild_id: int,
        from_user: Optional[int],
        to_user: Optional[int],
        amount: int,
        txn_type: TransactionType,
        note: str,
    ) -> None:
        await self.transactions.insert_one(
            {
                "guild_id": guild_id,
                "from_user": from_user,
                "to_user": to_user,
                "amount": amount,
                "type": txn_type,
                "timestamp": datetime.utcnow(),
                "note": note,
            }
        )