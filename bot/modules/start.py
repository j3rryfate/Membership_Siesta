from bot import CMD
from pyrogram import Client, filters
from ..helpers.message import send_message, fetch_user_details
from ..helpers.database.pg_impl import user_db # user_db ကို ထည့်သွင်း

import bot.helpers.translations as lang

@Client.on_message(filters.command(CMD.START))
async def start(bot, update):
    user = await fetch_user_details(update)
    
    # 1. User DB ထဲ ထည့်သွင်းခြင်း/ရှိမရှိ စစ်ဆေးခြင်း
    status = user_db.get_user_status(user['user_id'])
    if status:
        is_new_user = False
    else:
        is_new_user = True
    
    # ensure_user_exists ကို ခေါ်ပြီး DB ထဲ ထည့်သွင်း
    user_db.ensure_user_exists(
        user['user_id'], 
        user['user_name'] # username/mention
    )
    
    # 2. Admin ကို အကြောင်းကြားခြင်း (User အသစ်မှသာ)
    if is_new_user:
        admin_message = (
            f"🎉 **New User Joined!**\n"
            f"**Name:** {user['name']}\n"
            f"**Username:** @{update.from_user.username if update.from_user.username else 'N/A'}\n"
            f"**ID:** `{user['user_id']}`\n"
            f"**Status:** Not a Member yet."
        )
        # Config.ADMINS ထဲက ပထမဆုံး Admin ကိုပဲ ပို့ပါမယ်
        admin_id = list(bot.admin_ids)[0] if bot.admin_ids else None
        if admin_id:
            await send_message(
                user, 
                admin_message, 
                itype='text', 
                chat_id=admin_id
            )

    # 3. Welcome Message (မူရင်း code)
    msg = await bot.send_message(
        chat_id=update.chat.id,
        text=lang.s.WELCOME_MSG.format(
            update.from_user.first_name
        ),
        reply_to_message_id=update.id
    )
