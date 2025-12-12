import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

# Owner ka Telegram ID (int)
OWNER_ID = int(os.getenv("OWNER_ID"))

# Webhook server URL (jahan Flask chalega – Razorpay ye URL pe call karega)
WEBHOOK_PUBLIC_URL = os.getenv("WEBHOOK_PUBLIC_URL")
