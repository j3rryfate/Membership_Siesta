import asyncio
import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from bot import CMD
from bot.settings import bot_set
from bot.logger import LOGGER
from ..helpers.message import send_message, edit_message
from ..helpers.database.pg_impl import user_db
import bot.helpers.translations as lang

# Admin Check Filter
admin_only = filters.user(bot_set.admins) & filters.private # Admin တွေကို private chat ကနေသာ ခိုင်းစေခွင့်ပြု

@Client.on_message(filters.command("approve") & admin_only)
async def approve_handler(bot: Client, update: Message):
    if len(update.command) < 2:
        await send_message(update, "Usage: `/approve <user_id> [days]`\nDefault days is 30.", itype='text')
        return

    try:
        user_id = int(update.command[1])
        days = int(update.command[2]) if len(update.command) > 2 else 30
    except ValueError:
        await send_message(update, "Invalid User ID or Days format.", itype='text')
        return

    # 1. Membership Update
    new_expiry_date = user_db.update_user_membership(user_id, days)
    
    # 2. Pending Approval မှ ဖယ်ရှား
    user_db.remove_pending(user_id)
    
    # 3. Admin ကို အသိပေး
    admin_msg = f"✅ User ID `{user_id}` has been approved for **{days} days**.\nNew Expiry Date: `{new_expiry_date.strftime('%Y-%m-%d %H:%M:%S')}`"
    await send_message(update, admin_msg, itype='text')

    # 4. User ကို အသိပေး
    try:
        user_msg = (
            "🎉 **Subscription Approved!**\n\n"
            f"Your membership is now active for **{days} days**.\n"
            f"Expiry Date: `{new_expiry_date.strftime('%Y-%m-%d %H:%M:%S')}`\n"
            "You can now use all bot features."
        )
        await bot.send_message(user_id, user_msg)
    except Exception as e:
        await send_message(update, f"⚠️ Could not send message to user {user_id}. They might have blocked the bot.", itype='text')


@Client.on_message(filters.command("pending") & admin_only)
async def pending_handler(bot: Client, update: Message):
    pendings = user_db.get_all_pending_approvals()
    
    if not pendings:
        await send_message(update, "✅ No pending subscription requests.", itype='text')
        return
        
    text = f"**Pending Approvals: {len(pendings)} requests**\n\n"
    
    for i, p in enumerate(pendings, 1):
        # Telegram Message Link ကို ပြန်လည်တည်ဆောက်ခြင်း
        # Private Chat ID ကို Link အတွက် ပြင်ဆင်
        chat_id_for_link = str(p['proof_chat_id']).replace('-100', '')
        
        text += (
            f"**{i}. User:** [{p['username'] if p['username'] else p['user_id']}](tg://user?id={p['user_id']})\n"
            f"**ID:** `{p['user_id']}`\n"
            f"**Submitted:** {p['submitted_at'].strftime('%Y-%m-%d %H:%M')}\n"
            f"**Proof:** [Message Link](https://t.me/c/{chat_id_for_link}/{p['proof_message_id']})\n"
            f"**Command:** `/approve {p['user_id']} 30`\n\n"
        )

    await send_message(update, text, itype='text')


@Client.on_message(filters.command(["ban", "unban"]) & admin_only)
async def ban_unban_handler(bot: Client, update: Message):
    if len(update.command) < 2:
        await send_message(update, f"Usage: `/{update.command[0]} <user_id>`", itype='text')
        return
        
    try:
        user_id = int(update.command[1])
    except ValueError:
        await send_message(update, "Invalid User ID format.", itype='text')
        return

    is_ban = update.command[0] == "ban"
    
    user_db.set_user_banned_status(user_id, is_ban)
    
    action = "banned 🚫" if is_ban else "unbanned ✅"
    user_msg = f"Your access to the bot has been **{action}** by the admin."
    admin_msg = f"User ID `{user_id}` has been **{action}**."
    
    await send_message(update, admin_msg, itype='text')
    try:
        await bot.send_message(user_id, user_msg)
    except Exception:
        pass


@Client.on_message(filters.command("broadcast") & admin_only)
async def broadcast_handler(bot: Client, update: Message):
    if not update.reply_to_message:
        await send_message(update, "Please reply to the message you want to broadcast.", itype='text')
        return
    
    users = user_db.get_all_users()
    sent_count = 0
    failed_count = 0
    
    broadcast_msg = await send_message(update, f"Broadcasting message to {len(users)} users...", itype='text')

    for user_id in users:
        try:
            # Admin တွေကို မပို့တော့ပါ
            if user_id in bot_set.admins:
                continue
                
            await update.reply_to_message.copy(user_id)
            sent_count += 1
            await asyncio.sleep(0.1) # FloodWait ကို ရှောင်ရှားရန်
        except Exception as e:
            if "blocked" in str(e).lower():
                 pass # Block လုပ်ထားရင် ဖျောက်
            else:
                 LOGGER.error(f"Broadcast failed for {user_id}: {e}")
                 failed_count += 1
        
    final_msg = (
        f"**Broadcast Completed!**\n"
        f"**Total Users (including non-members):** {len(users)}\n"
        f"**Sent:** {sent_count}\n"
        f"**Failed (Blocked/Error):** {failed_count}"
    )
    await edit_message(broadcast_msg, final_msg)
