import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables")

if not DATABASE_URL:
    raise ValueError("No DATABASE_URL found in environment variables")