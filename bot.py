import os
import base64
import requests
from requests.auth import HTTPBasicAuth

import razorpay
from pyrogram import idle
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import (
    API_ID, API_HASH, BOT_TOKEN,
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,
    OWNER_ID, WEBHOOK_PUBLIC_URL
)
from database import init_db, add_item, get_all_items, get_item

# temp memory
user_state = {}
temp_data = {}

app = Client("payment-bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

@app.on_message(filters.command("start"))
async def start_handler(client, message):
    items = get_all_items()
    if not items:
        await message.reply_text("Filhaal koi item available nahi hai.")
        return

    buttons = []
    for item_id, button_name, price in items:
        buttons.append([
            InlineKeyboardButton(
                text=f"{button_name} - ₹{price // 100}",
                callback_data=f"buy_{item_id}"
            )
        ])

    await message.reply_text(
        "Namaste! Kya chahiye? Neeche se select karo 👇",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# Owner-only add
@app.on_message(filters.command("add") & filters.user(OWNER_ID))
async def add_item_command(client, message):
    user_state[message.from_user.id] = "ASK_TYPE"
    temp_data[message.from_user.id] = {}
    await message.reply_text("Kya add karna hai? `video` ya `link` likho.", quote=True)

@app.on_message(filters.user(OWNER_ID))
async def owner_flow(client, message):
    uid = message.from_user.id
    if uid not in user_state:
        return

    state = user_state[uid]

    if state == "ASK_TYPE":
        text = (message.text or "").strip().lower()
        if text not in ["video", "link"]:
            await message.reply_text("Sirf `video` ya `link` likho.")
            return
        temp_data[uid]["type"] = text
        user_state[uid] = "ASK_CONTENT"
        if text == "video":
            await message.reply_text("Ab wo video bhejo jo sell karni hai.")
        else:
            await message.reply_text("Ab wo URL bhejo jo sell karni hai.")
        return

    if state == "ASK_CONTENT":
        ctype = temp_data[uid]["type"]
        if ctype == "video":
            if not message.video:
                await message.reply_text("Kripya video bhejo.")
                return
            temp_data[uid]["file_id"] = message.video.file_id
            temp_data[uid]["url"] = None
        else:
            if not message.text:
                await message.reply_text("Kripya link (URL) text me bhejo.")
                return
            temp_data[uid]["url"] = message.text.strip()
            temp_data[uid]["file_id"] = None

        user_state[uid] = "ASK_BUTTON_NAME"
        await message.reply_text("Button ka naam kya rakhe? (jaise: Video 1)")
        return

    if state == "ASK_BUTTON_NAME":
        temp_data[uid]["button_name"] = message.text.strip()
        user_state[uid] = "ASK_PRICE"
        await message.reply_text("Price kitna rakhe? (₹ me number likho, jaise 299)")
        return

    if state == "ASK_PRICE":
        try:
            price = int(message.text.strip())
        except:
            await message.reply_text("Valid number likho, jaise 299")
            return

        data = temp_data[uid]
        add_item(
            button_name=data["button_name"],
            content_type=data["type"],
            file_id=data["file_id"],
            url=data["url"],
            price_rupees=price
        )

        await message.reply_text(
            f"Item saved ✅\n\nName: {data['button_name']}\nType: {data['type']}\nPrice: ₹{price}"
        )

        user_state.pop(uid, None)
        temp_data.pop(uid, None)
        return

@app.on_callback_query(filters.regex(r"^buy_(\d+)$"))
async def buy_item(client, callback_query):
    item_id = int(callback_query.data.split("_")[1])
    item = get_item(item_id)
    if not item:
        await callback_query.answer("Item nahi mila.", show_alert=True)
        return

    _id, button_name, content_type, file_id, url, price = item
    user = callback_query.from_user
    amount = price  # paise expected

    # 1) Create payment link
    try:
        payment_link = razorpay_client.payment_link.create({
            "amount": amount,
            "currency": "INR",
            "description": button_name,
            "customer": {
                "name": user.first_name or "",
                # If possible, use a real email/phone for better UX:
                "email": "test@example.com"
            },
            "notify": {"sms": False, "email": False},
            "notes": {"telegram_user_id": str(user.id), "item_id": str(item_id)}
        })
    except Exception as e:
        print("ERROR creating payment link:", e)
        await callback_query.message.reply_text("Payment link banaate waqt error aaya. Thodi der me try karo.")
        await callback_query.answer()
        return

    print("DEBUG payment_link:", payment_link)

    link_id = payment_link.get("id")
    short_url = payment_link.get("short_url") or payment_link.get("shortlink") or payment_link.get("shortLink")

    if not link_id or not short_url:
        # If response missing, show full response for debugging and abort
        print("Payment link missing id/short_url. Full response:", payment_link)
        await callback_query.message.reply_text("Payment link create nahi hua. Contact admin.")
        await callback_query.answer()
        return

    # 2) Try to fetch detailed link data (may contain qr info)
    try:
        link_data = razorpay_client.payment_link.fetch(link_id)
    except Exception as e:
        print("WARN unable to fetch payment_link details:", e)
        link_data = {}

    print("DEBUG link_data:", link_data)

    # 3) Try to get QR from link_data (some accounts don't have this)
    qr_base64 = None
    # multiple possible locations
    if isinstance(link_data, dict):
        qr_base64 = link_data.get("qr", {}).get("image") or link_data.get("image") or link_data.get("qr_image") or None

    # 4) If no QR in link_data, attempt Razorpay QR API (v1/payments/qr_codes)
    qr_file_path = None
    if not qr_base64:
        try:
            qr_payload = {
                "type": "upi_qr",            # use upi_qr or omit depending on your need
                "name": f"Payment for {button_name}",
                "usage": "single_use",
                "fixed_amount": True,
                "amount": amount,
                "currency": "INR",
                "notes": {"link_id": link_id, "item_id": str(item_id)}
            }
            resp = requests.post(
                "https://api.razorpay.com/v1/payments/qr_codes",
                auth=HTTPBasicAuth(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
                json=qr_payload,
                timeout=15
            )
            print("DEBUG qr_api status:", resp.status_code, resp.text[:1000])
            if resp.status_code in (200, 201):
                qr_json = resp.json()
                # image may be present as 'image' (base64) or 'image_content' or an URL in 'short_url'
                qr_base64 = qr_json.get("image") or qr_json.get("image_content") or None
                qr_url = qr_json.get("short_url") or qr_json.get("url") or qr_json.get("qr_url")
                # if image_content is a URL, use that directly
                if qr_base64 and qr_base64.startswith("http"):
                    qr_file_path = None
                    qr_remote_url = qr_base64
                elif qr_base64:
                    qr_bytes = base64.b64decode(qr_base64)
                    qr_file_path = f"payment_qr_{link_id}.png"
                    with open(qr_file_path, "wb") as f:
                        f.write(qr_bytes)
                elif qr_url:
                    # QR API returned a URL
                    qr_file_path = None
                    qr_remote_url = qr_url
                else:
                    qr_file_path = None
        except Exception as e:
            print("WARN QR API failed:", e)

    else:
        # We already have base64 from link_data
        try:
            qr_bytes = base64.b64decode(qr_base64)
            qr_file_path = f"payment_qr_{link_id}.png"
            with open(qr_file_path, "wb") as f:
                f.write(qr_bytes)
        except Exception as e:
            print("WARN could not decode qr_base64:", e)
            qr_file_path = None

    # 5) Send to user: prefer local file, then remote URL, then fallback to short_url
    caption_text = (
        f"💵 *Payment Required*\n\n"
        f"Item: *{button_name}*\n"
        f"Amount: ₹{amount//100}\n\n"
        f"🔗 Payment Link:\n{short_url}\n\n"
        f"📌 You can pay using Payment Link or QR."
    )

    try:
        if qr_file_path and os.path.exists(qr_file_path):
            # send local file
            with open(qr_file_path, "rb") as photo:
                await callback_query.message.reply_photo(photo, caption=caption_text)
            # remove temporary file
            try:
                os.remove(qr_file_path)
            except:
                pass
        else:
            # if qr_remote_url available, try it
            qr_remote_url = locals().get("qr_remote_url", None)
            if qr_remote_url:
                await callback_query.message.reply_photo(qr_remote_url, caption=caption_text)
            else:
                # final fallback: just send short link
                await callback_query.message.reply_text(f"Payment Link (QR unavailable):\n{short_url}")
    except Exception as e:
        print("ERROR sending payment info:", e)
        await callback_query.message.reply_text(f"Payment Link:\n{short_url}")

    await callback_query.answer()

if __name__ == "__main__":
    init_db()
    try:
        app.start()
        print("Bot started...")
        idle()  # blocks until SIGINT/SIGTERM
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        print("Bot stopped.")
