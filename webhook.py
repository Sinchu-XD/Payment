from flask import Flask, request, abort
import razorpay
import hmac
import hashlib
import json

from config import (
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
    BOT_TOKEN, API_ID, API_HASH, OWNER_ID
)
from database import get_item
from pyrogram import Client

app = Flask(__name__)

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

bot = Client("payment-bot-webhook", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


def verify_signature(request_body, signature):
    expected = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        request_body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.route("/webhook", methods=["POST"])
def webhook():
    payload = request.data
    signature = request.headers.get("X-Razorpay-Signature")

    if not signature or not verify_signature(payload, signature):
        abort(400)

    data = json.loads(payload.decode("utf-8"))

    event = data.get("event")
    if event == "payment_link.paid":
        payment_link = data.get("payload", {}).get("payment_link", {}).get("entity", {})
        notes = payment_link.get("notes", {})
        telegram_user_id = int(notes.get("telegram_user_id"))
        item_id = int(notes.get("item_id"))

        item = get_item(item_id)
        if not item:
            return "item not found", 200

        _id, button_name, content_type, file_id, url, price = item

        async def send_messages():
            await bot.start()

            # Customer ko message + content
            text = f"✅ Payment Successful!\n\nItem: {button_name}\nAmount: ₹{price // 100}"
            await bot.send_message(telegram_user_id, text)

            if content_type == "video" and file_id:
                await bot.send_video(telegram_user_id, file_id, caption=button_name)
            elif content_type == "link" and url:
                await bot.send_message(telegram_user_id, f"Your Link:\n{url}")

            # Owner ko notification
            owner_text = (
                f"🤑 New Order!\n\n"
                f"Buyer ID: `{telegram_user_id}`\n"
                f"Item: {button_name}\n"
                f"Amount: ₹{price // 100}"
            )
            await bot.send_message(OWNER_ID, owner_text)

            await bot.stop()

        import asyncio
        asyncio.get_event_loop().create_task(send_messages())

    return "ok", 200


if __name__ == "__main__":
    bot.start()
    app.run(host="0.0.0.0", port=8000)
  
