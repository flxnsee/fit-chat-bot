from concurrent.futures import wait
import logging
import math
from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorClient as MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError
from config import DATABASE_URL
from datetime import datetime, timedelta
from bson import ObjectId
from pymongo import ReturnDocument
import random

logger = logging.getLogger(__name__)

try:
    client = MongoClient(DATABASE_URL, serverSelectionTimeoutMS=5000)
    logger.info("Connected to MongoDB successfully")
except ConnectionFailure as e:
    logger.error(f"Could not connect to MongoDB: {e}")
    raise
except Exception as e:
    logger.error(f"An unexpected error occurred while connecting to MongoDB: {e}")
    raise

db = client['fit_chat_bot']
users_collection = db['users']
letters_collection = db['letters']

async def init_indexes():
    try:
        await users_collection.create_index("user_id", unique=True)
        await letters_collection.create_index("recipient_id")
        await letters_collection.create_index("sender_id")
        await letters_collection.create_index([("deliver_at", 1), ("status", 1)])
        await users_collection.create_index("hobbies")
        await users_collection.create_index("course")

        logger.info("Indexes created successfully")
    except PyMongoError as e:
        logger.error(f"Error creating indexes: {e}")

async def store_user(user_id: int, hobbies: list, course: str = None):
    try:
        update_data = {"hobbies": hobbies}

        if course:
            update_data["course"] = course

        await users_collection.update_one(
            {'user_id': user_id},
            {
                "$set": update_data,
                "$setOnInsert": {
                    "is_active": True,
                    "is_admin": False,
                    "settings": {"filter_course": False}
                }
            },
            upsert=True
        )

        logger.info(f"User {user_id} stored/updated successfully")

    except PyMongoError as e:
        logger.error(f"Error storing user: {e}")

async def check_user_exists(user_id: int) -> bool:
    try:
        user = await users_collection.find_one({'user_id': user_id})

        return bool(user)
    
    except PyMongoError as e:
        logger.error(f"Error checking if user exists: {e}")

        return False

async def get_user(user_id: int) -> dict:
    try:
        user = await users_collection.find_one({'user_id': user_id})

        return user
    
    except PyMongoError as e:
        logger.error(f"Error retrieving user: {e}")

        return None

async def can_send_letter(user_id: int) -> bool:
    try:
        user = await get_user(user_id)

        if not user:
            return True
        
        last_sent = user.get('last_letter_sent')

        if not last_sent or last_sent.date() < datetime.now().date():
            return True
        
        daily_count = user.get('daily_letters_count', 0)

        return daily_count < 3
    
    except PyMongoError as e:
        logger.error(f"Error checking if user can send letter: {e}")

        return False
    
async def get_remaining_limit(user_id: int) -> int:
    try:
        user = await get_user(user_id)

        if not user:
            return 3
        
        last_sent = user.get('last_letter_sent')

        if not last_sent or last_sent.date() < datetime.now().date():
            return 3
        
        used = user.get('daily_letters_count', 0)

        return max(0, 3 - used)
    
    except PyMongoError as e:
        logger.error(f"Error retrieving remaining limit for user {user_id}: {e}")

        return 0

async def find_recipient(sender_id: int, sender_hobbies: list, sender_course: str = None) -> dict | None:
    try:
        sender = await get_user(sender_id)

        if not sender:
            return None
        
        communicated_users = await get_users_communicated_with(sender_id)
        settings = sender.get('settings', {})
        only_my_course = settings.get('filter_course', False)
        excluded_users = [sender_id] + communicated_users
        
        base_match = {
            "user_id": {"$nin": excluded_users},
            "is_active": {"$ne": False}
        }

        if only_my_course and sender_course:
            base_match["course"] = sender_course

        pipeline = [
            {
                "$match": {
                    **base_match,
                    "hobbies": {"$in": sender_hobbies}
                }
            },
            {
                "$project": {
                    "user_id": 1,
                    "hobbies": 1,
                    "course": 1,
                    "common_count": {
                        "$size": {"$setIntersection": ["$hobbies", sender_hobbies]}
                    }
                }
            },
            {"$sort": {"common_count": -1}},
            {"$limit": 10}
        ]

        cursor = users_collection.aggregate(pipeline)
        candidates = await cursor.to_list(length=10)

        if candidates:
            return random.choice(candidates)
        
        fallback_pipeline = [
            {"$match": base_match},
            {"$sample": {"size": 1}}
        ]

        fallback_cursor = users_collection.aggregate(fallback_pipeline)
        fallback_candidates = await fallback_cursor.to_list(length=1)

        return fallback_candidates[0] if fallback_candidates else None
    
    except PyMongoError as e:
        logger.error(f"Error finding recipient: {e}")
        
        return None

async def create_letter(sender_id: int, recipient_id: int, content: str, delay_hours: int = 2, parent_id: str = None, consume_quota: bool = True):
    try:
        deliver_at = datetime.now() + timedelta(hours = delay_hours)

        # Генерація номеру для анонімного імені
        anonymous_number = await get_next_anonymous_number(recipient_id)
        default_nickname = f"Анонім {anonymous_number}"

        letter = {
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "content": content,
            "status": "pending",
            "is_read": False,
            "is_archived": False,
            "parent_id": ObjectId(parent_id) if parent_id else None,
            "created_at": datetime.now(),
            "deliver_at": deliver_at,
            "nickname": default_nickname
        }

        await letters_collection.insert_one(letter)

        if consume_quota:
            user = await get_user(sender_id)
            last_sent = user.get('last_letter_sent')
            current_count = user.get('daily_letters_count', 0)
            now = datetime.now()

            if not last_sent or last_sent.date() < now.date():
                new_count = 1
            else:
                new_count = current_count + 1

            await users_collection.update_one(
                {'user_id': sender_id},
                {'$set': {'last_letter_sent': now,
                          'daily_letters_count': new_count}
                },
            )
        else:
            await users_collection.update_one(
                {'user_id': sender_id},
                {'$set': {'last_letter_sent': datetime.now()}}
            )

        return deliver_at
    
    except PyMongoError as e:
        logger.error(f"Error creating letter: {e}")

        raise

async def get_letters(limit: int = 50):
    try:
        now = datetime.now()

        return await letters_collection.find({
            "status": "pending",
            "deliver_at": {"$lte": now}
        }).limit(limit).to_list(length=None)
    
    except PyMongoError as e:
        logger.error(f"Error retrieving due letters: {e}")

        return []

async def mark_letter_delivered(letter_id):
    try:
        await letters_collection.update_one(
        {'_id': letter_id},
        {
            '$set': {
                'status': 'delivered',
                'delivered_at': datetime.now()
            }
        }
    )
        
    except PyMongoError as e:
        logger.error(f"Error marking letter as delivered: {e}")

async def get_inbox(user_id: int, page: int = 0, page_size: int = 5) -> List[dict]:
    try:
        query = {
            "recipient_id": user_id,
            "status": "delivered",
            "is_archived": {"$ne": True}
        }

        total_count = await letters_collection.count_documents(query)

        cursor = letters_collection.find(query)\
            .sort([("is_read", 1),("delivered_at", -1)])\
                .skip(page * page_size)\
                    .limit(page_size)
        
        letters = await cursor.to_list(length = page_size)

        return letters, total_count
    
    except PyMongoError as e:
        logger.error(f"Error retrieving inbox for user {user_id}: {e}")

        return [], 0
async def get_letter(letter_id: str):
    try:
        if not ObjectId.is_valid(letter_id):
            return None
    
        return await letters_collection.find_one({'_id': ObjectId(letter_id)})
    
    except PyMongoError as e:
        logger.error(f"Error retrieving letter {letter_id}: {e}")

        return None

async def delete_letter(letter_id: str):
    try:
        if not ObjectId.is_valid(letter_id):
            return
    
        await letters_collection.delete_one({'_id': ObjectId(letter_id)})
    
    except PyMongoError as e:
        logger.error(f"Error deleting letter {letter_id}: {e}")

        return False
    
async def mark_letter_read(letter_id: str):
    if not ObjectId.is_valid(letter_id):
        return
    
    await letters_collection.update_one(
        {'_id': ObjectId(letter_id)},
        {
            '$set': {
                'is_read': True
            }
        }
    )

async def archive_letter(letter_id: str):
    if not ObjectId.is_valid(letter_id):
        return
    
    await letters_collection.update_one(
        {'_id': ObjectId(letter_id)},
        {
            '$set': {
                'is_archived': True
            }
        }
    )

async def archive_all_letters(user_id: int):
    """Архівувати всі доставлені листи користувача"""
    try:
        result = await letters_collection.update_many(
            {
                'recipient_id': user_id,
                'status': 'delivered',
                'is_archived': {'$ne': True}
            },
            {
                '$set': {
                    'is_archived': True
                }
            }
        )
        return result.modified_count
    except PyMongoError as e:
        logger.error(f"Error archiving all letters for user {user_id}: {e}")
        return 0

async def get_users_communicated_with(user_id: int) -> list[int]:
    """Отримати список user_id з якими користувач обмінювався листами"""
    try:
        pipeline = [
            {
                "$match": {
                    "$or": [
                        {"sender_id": user_id},
                        {"recipient_id": user_id}
                    ],
                    "status": "delivered"
                }
            },
            {
                "$project": {
                    "other_user": {
                        "$cond": {
                            "if": {"$eq": ["$sender_id", user_id]},
                            "then": "$recipient_id",
                            "else": "$sender_id"
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": "$other_user"
                }
            }
        ]
        
        cursor = letters_collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        
        return [doc['_id'] for doc in results]
    
    except PyMongoError as e:
        logger.error(f"Error getting communicated users for {user_id}: {e}")
        return []
    
async def get_dialogue_history(user_id: int, other_user_id: int, limit: int = 20):
    try:
        query = {
            "$or": [
                {"sender_id": user_id, "recipient_id": other_user_id},
                {"sender_id": other_user_id, "recipient_id": user_id}
            ],
            "status": "delivered"
        }

        cursor = letters_collection.find(query).sort("created_at", -1).limit(limit)

        return await cursor.to_list(length = limit)
    
    except PyMongoError as e:
        logger.error(f"Error retrieving dialogue history between {user_id} and {other_user_id}: {e}")

        return []

async def get_dialogue_history_page(user_id: int, other_user_id: int, page: int = 0, page_size: int = 10):
    try:
        query = {
            "$or": [
                {"sender_id": user_id, "recipient_id": other_user_id},
                {"sender_id": other_user_id, "recipient_id": user_id}
            ],
            "status": "delivered"
        }

        total_count = await letters_collection.count_documents(query)
        cursor = letters_collection.find(query).sort("created_at", 1).skip(page * page_size).limit(page_size)
        items = await cursor.to_list(length=page_size)

        return items, total_count

    except PyMongoError as e:
        logger.error(f"Error retrieving dialogue history page between {user_id} and {other_user_id}: {e}")

        return [], 0

async def mark_letter_failed(letter_id: str, reason: str):
    try:
        if not ObjectId.is_valid(letter_id):
            return
    
        await letters_collection.update_one(
            {'_id': ObjectId(letter_id)},
            {
                '$set': {
                    'status': 'failed',
                    'failure_reason': reason,
                    'failed_at': datetime.now()
                }
            }
        )

    except PyMongoError as e:
        logger.error(f"Error marking letter {letter_id} as failed: {e}")

async def activate_user(user_id: int):
    try:
        await users_collection.update_one(
            {'user_id': user_id},
            {'$set': {
                'is_active': True
                },
            },
            upsert=True
        )

    except PyMongoError as e:
        logger.error(f"Error activating user {user_id}: {e}")

async def deactivate_user(user_id: int):
    try:
        await users_collection.update_one(
            {'user_id': user_id},
            {'$set': {
                'is_active': False
                },
            },
        )

    except PyMongoError as e:
        logger.error(f"Error deactivating user {user_id}: {e}")

async def set_admin(user_id: int, is_admin: bool = True):
    try:
        await users_collection.update_one(
            {'user_id': user_id},
            {'$set': {
                'is_admin': is_admin
                },
            },
            upsert=True
        )

    except PyMongoError as e:
        logger.error(f"Error setting admin status for user {user_id}: {e}")

async def get_admins() -> List[int]:
    try:
        cursor = users_collection.find({'is_admin': True})
        admins = await cursor.to_list(length = None)

        return [admin['user_id'] for admin in admins]  

    except PyMongoError as e:
        logger.error(f"Error retrieving admins: {e}")

        return [] 

async def is_user_admin(user_id: int) -> bool:
    try:
        user = await users_collection.find_one({'user_id': user_id, 'is_admin': True})
    
        return bool(user)

    except PyMongoError as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}")

        return False

async def toggle_filter_course(user_id: int) -> bool:
    try:
        user = await get_user(user_id)
        current_setting = user.get('settings', {}).get('filter_course', False) if user else False
        new_setting = not current_setting

        await users_collection.update_one(
            {'user_id': user_id},
            {'$set': {f'settings.filter_course': new_setting}},
            upsert=True
        )

        return new_setting
    
    except PyMongoError as e:
        logger.error(f"Error toggling filter_course for user {user_id}: {e}")

        return False

async def get_user_settings(user_id: int):
    try:
        user = await get_user(user_id)

        return user.get('settings', {'filter_course': False}) if user else {'filter_course': False}

    except PyMongoError as e:
        logger.error(f"Error retrieving settings for user {user_id}: {e}")

        return {'filter_course': False}

async def report_user_letter(letter_id: str, reported_id: int):
    try:
        if not ObjectId.is_valid(letter_id):
            return
    
        letter = await letters_collection.find_one({'_id': ObjectId(letter_id)})

        if not letter:
            return None
        
        await letters_collection.update_one(
            {'_id': ObjectId(letter_id)},
            {'$set': {
                'status': 'reported',
                'reported_by': reported_id
                },
            },
        )

        return letter
    
    except PyMongoError as e:
        logger.error(f"Error reporting letter {letter_id}: {e}")

        return None

async def is_user_banned(user_id: int) -> bool:
    try:
        user = await users_collection.find_one({'user_id': user_id, 'is_active': False})

        return bool(user)
    
    except PyMongoError as e:
        logger.error(f"Error checking if user {user_id} is banned: {e}")

        return False

async def get_bot_stats():
    try:
        total_users = await users_collection.count_documents({})
        actve_users = await users_collection.count_documents({'is_active': {"$ne": False}})
        banned_users = total_users - actve_users
        total_letters = await letters_collection.count_documents({})
        delivered_letters = await letters_collection.count_documents({'status': 'delivered'})

        return {
            "total_users": total_users,
            "active_users": actve_users,
            "banned_users": banned_users,
            "total_letters": total_letters,
            "delivered_letters": delivered_letters
        }
    
    except PyMongoError as e:
        logger.error(f"Error retrieving bot stats: {e}")

        return {}

async def get_all_users_cursor():
    try:
        return users_collection.find({"is_active": {"$ne": False}})
    
    except PyMongoError as e:
        logger.error(f"Error retrieving all users cursor: {e}")

        return None
    
async def get_user_stats(user_id: int):
    try:
        total_sent = await letters_collection.count_documents({'sender_id': user_id})
        total_received = await letters_collection.count_documents({
            'recipient_id': user_id,
            'status': 'delivered'
        })

        return {
            "total_sent": total_sent,
            "total_received": total_received
        }
    
    except PyMongoError as e:
        logger.error(f"Error retrieving stats for user {user_id}: {e}")

        return {}
    
async def get_active_reports():
    try:
        return await letters_collection.find({'status': 'reported'}).to_list(length = None)
    
    except PyMongoError as e:
        logger.error(f"Error retrieving active reports: {e}")

        return []
    
async def warn_user(user_id: int):
    try:
        result = await users_collection.find_one_and_update(
            {'user_id': user_id},
            {'$inc': {'warnings': 1}},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )

        return result.get('warnings', 1)
    
    except PyMongoError as e:
        logger.error(f"Error warning user {user_id}: {e}")

        return 0
    
async def close_report(letter_id: str, admin_id: int, resolution: str):
    try:
        if not ObjectId.is_valid(letter_id):
            return False
        
        await letters_collection.update_one(
            {'_id': ObjectId(letter_id)},
            {
                '$set': {
                    'status': 'resolved',
                    'report_resolution': resolution,
                    'report_closed_by': admin_id,
                    'report_closed_at': datetime.now()
                }
            }
        )
        return True
    
    except PyMongoError as e:
        logger.error(f"Error closing report for letter {letter_id}: {e}")

        return False

async def get_dialogue_history_with_pagination(user_id: int, other_user_id: int, page: int = 0, letters_per_page: int = 2) -> tuple:
    """
    Отримати всю історію листів з користувачем для однієї сторінки.
    Показує фіксовану кількість листів на сторінку.
    
    Повертає кортеж:
    - page_letters: список листів, які вмістилися на цій сторінці
    - total_pages: загальна кількість сторінок
    - current_page: поточна сторінка (0-indexed)
    - total_letters: загальна кількість листів в діалозі
    """
    try:
        query = {
            "$or": [
                {"sender_id": user_id, "recipient_id": other_user_id},
                {"sender_id": other_user_id, "recipient_id": user_id}
            ],
            "status": "delivered"
        }

        total_letters = await letters_collection.count_documents(query)
        total_pages = max(1, math.ceil(total_letters / letters_per_page))
        
        if page >= total_pages:
            page = total_pages - 1
        if page < 0:
            page = 0
        
        skip = page * letters_per_page
        cursor = letters_collection.find(query).sort("created_at", 1).skip(skip).limit(letters_per_page)
        page_letters = await cursor.to_list(length=letters_per_page)
        
        return page_letters, total_pages, page, total_letters
    
    except PyMongoError as e:
        logger.error(f"Error getting dialogue history with pagination: {e}")
        return [], 0, 0, 0

async def get_next_anonymous_number(recipient_id: int) -> int:
    """Отримати наступний номер для анонімного імені"""
    try:
        # Рахуємо листи від цього користувача, які вже отримали
        count = await letters_collection.count_documents({
            "recipient_id": recipient_id,
            "status": "delivered"
        })
        return count + 1
    except PyMongoError as e:
        logger.error(f"Error getting next anonymous number: {e}")
        return 1

async def update_letter_nickname(letter_id: str, new_nickname: str) -> bool:
    """Оновити нікнейм листа"""
    try:
        if not ObjectId.is_valid(letter_id):
            return False
        
        # Обмеження довжини нікнейму
        if len(new_nickname) > 30:
            new_nickname = new_nickname[:30]
        
        if len(new_nickname.strip()) == 0:
            return False
        
        result = await letters_collection.update_one(
            {'_id': ObjectId(letter_id)},
            {
                '$set': {
                    'nickname': new_nickname.strip()
                }
            }
        )
        return result.modified_count > 0
    except PyMongoError as e:
        logger.error(f"Error updating letter nickname: {e}")
        return False

async def get_all_user_letters(user_id: int, page: int = 0, page_size: int = 4):
    """Отримати всі листи користувача (як отримані, так і відправлені)"""
    try:
        query = {
            "$or": [
                {"recipient_id": user_id, "status": "delivered"},
                {"sender_id": user_id, "status": "delivered"}
            ]
        }

        total_count = await letters_collection.count_documents(query)

        cursor = letters_collection.find(query)\
            .sort([("created_at", -1)])\
                .skip(page * page_size)\
                    .limit(page_size)
        
        letters = await cursor.to_list(length=page_size)

        return letters, total_count
    
    except PyMongoError as e:
        logger.error(f"Error retrieving all user letters {user_id}: {e}")
        return [], 0