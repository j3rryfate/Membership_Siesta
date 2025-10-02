from pyrogram import Client, filters
from pyrogram.types import Message
from bot import CMD
from bot.settings import bot_set
from ..helpers.message import send_message, fetch_user_details
from ..helpers.database.pg_impl import user_db
import bot.helpers.translations as lang

@Client.on_message(filters.command("subscription"))
async def subscription_handler(bot: Client, update: Message):
    user = await fetch_user_details(update)
    
    # Admin တွေက /subscription သုံးစရာ မလို
    if user['user_id'] in bot_set.admins:
        await send_message(user, "You are an Admin. No subscription needed.", itype='text')
        return

    # 1. ပုံ ရှိမရှိ စစ်ဆေး
    if not update.reply_to_message or not update.reply_to_message.photo:
        await send_message(
            user, 
            "**❌ Please reply to the payment receipt photo** with the `/subscription` command.", 
            itype='text'
        )
        return

    # 2. ငွေပေးချေမှုအထောက်အထားကို သိမ်းဆည်း
    proof_msg = update.reply_to_message
    
    # proof ရဲ့ file_id (ပုံ) နဲ့ message ID ကို သိမ်းဆည်း
    user_db.add_pending_approval(
        user_id=user['user_id'],
        username=user['user_name'],
        proof_chat_id=proof_msg.chat.id,
        proof_message_id=proof_msg.id
    )

    # 3. User ကို အသိပေး
    await send_message(
        user,
        "✅ **Payment proof submitted!**\n\n"
        "Your request has been sent to the admin for manual approval. "
        "We will notify you once your subscription is active. Thank you!",
        itype='text'
    )
    
    # 4. Admin ကို အကြောင်းကြား
    admin_message = (
        f"🔔 **New Subscription Request!**\n"
        f"**User:** [{user['name']}](tg://user?id={user['user_id']})\n"
        f"**ID:** `{user['user_id']}`\n"
        f"**Action:** Please check the attached photo and use `/approve {user['user_id']} [days]` to approve."
    )
    
    # Admin ကို ပုံကို Fowarding လုပ်ပြီး စာပို့
    for admin_id in bot_set.admins:
        try:
            # Proof message ကို admin သို့ Forward လုပ်ခြင်း (မူရင်းပုံကို မြင်စေရန်)
            await bot.forward_messages(
                chat_id=admin_id,
                from_chat_id=proof_msg.chat.id,
                message_ids=proof_msg.id
            )
            
            await bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                disable_web_page_preview=True
            )
        except Exception as e:
            # admin ကို စာပို့မရရင် ignore
            pass
