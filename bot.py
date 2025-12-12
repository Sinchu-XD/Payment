import asyncio
import razorpay
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config import (
    API_ID, API_HASH, BOT_TOKEN,
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,
    OWNER_ID, WEBHOOK_PUBLIC_URL
)
from database import init_db, add_item, get_all_items, get_item

# States temporary memory
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

    # Inline buttons banao
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


# Only owner can add items
@app.on_message(filters.command("add") & filters.user(OWNER_ID))
async def add_item_command(client, message):
    user_state[message.from_user.id] = "ASK_TYPE"
    temp_data[message.from_user.id] = {}
    await message.reply_text("Kya add karna hai? `video` ya `link` likho.",
                             quote=True)


@app.on_message(filters.user(OWNER_ID))
async def owner_flow(client, message):
    uid = message.from_user.id
    if uid not in user_state:
        return

    state = user_state[uid]

    # Step 1: Ask type
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

    # Step 2: Content
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

    # Step 3: Button name
    if state == "ASK_BUTTON_NAME":
        temp_data[uid]["button_name"] = message.text.strip()
        user_state[uid] = "ASK_PRICE"
        await message.reply_text("Price kitna rakhe? (₹ me number likho, jaise 299)")
        return

    # Step 4: Price
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


# Customer clicked on item button
@app.on_callback_query(filters.regex(r"^buy_(\d+)$"))
async def buy_item(client, callback_query):
    item_id = int(callback_query.data.split("_")[1])
    item = get_item(item_id)
    if not item:
        await callback_query.answer("Item nahi mila.", show_alert=True)
        return

    _id, button_name, content_type, file_id, url, price = item

    user = callback_query.from_user
    amount = price  # already in paise

    # Razorpay payment link create
    payment_link = razorpay_client.payment_link.create({
        "amount": amount,
        "currency": "INR",
        "description": button_name,
        "customer": {
            "name": user.first_name or "",
            "email": "test@example.com"  # agar email log karna ho to pehle user se pooch sakte ho
        },
        "notify": {
            "sms": False,
            "email": False
        },
        "callback_url": WEBHOOK_PUBLIC_URL,  # optional - but we'll use webhook mainly
        "callback_method": "get",
        "notes": {
            "telegram_user_id": str(user.id),
            "item_id": str(item_id)
        }
    })

    await callback_query.message.reply_text(
        f"Payment Details:\n\nItem: {button_name}\nAmount: ₹{amount // 100}\n\n"
        f"Payment link: {payment_link['short_url']}\n\n"
        "Payment hone ke baad aapko yahi pe content mil jayega ✅"
    )

    await callback_query.answer()
    

async def main():
    init_db()
    await app.start()
    print("Bot started...")
    await idle()

from pyrogram import idle

if __name__ == "__main__":
    asyncio.run(main())
  
