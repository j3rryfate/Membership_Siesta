from config import Config

from pyrogram import Client

from .logger import LOGGER
from .settings import bot_set

import asyncio 
from .helpers.database.pg_impl import user_db
import datetime


plugins = dict(
    root="bot/modules"
)

# Membership Expiry Checker Task
async def check_membership_expiry():
    # နေ့တိုင်း (24 နာရီတစ်ခါ) စစ်ဆေးရန်
    while True:
        await asyncio.sleep(24 * 60 * 60) 
        
        LOGGER.info("MEMBERSHIP: Starting expiry check...")
        
        all_users = user_db.get_all_users()
        expired_count = 0
        now = datetime.datetime.now()
        
        for user_id in all_users:
            # Admin တွေကို စစ်ဆေးရန်မလို
            if user_id in Config.ADMINS:
                continue
                
            status = user_db.get_user_status(user_id)
            
            # Member ဖြစ်ပြီး၊ expiry_date ရှိပြီး၊ expiry_date က လက်ရှိအချိန်ထက်စောနေရင်
            if status and status['is_member'] and status['expiry_date'] and status['expiry_date'] < now:
                # သက်တမ်းကုန်ရင် is_member ကို False ပြန်လုပ်
                user_db.set_expired(user_id)
                expired_count += 1
                LOGGER.info(f"MEMBERSHIP: User {user_id} expired and set to non-member.")
                try:
                    await aio.send_message(
                        user_id, 
                        "⏰ **Your subscription has expired!**\n\n"
                        "Please use the `/subscription` command with a new payment proof to renew your membership."
                    )
                except Exception as e:
                    # user က block ထားရင် ဆက်လုပ်
                    pass 

        LOGGER.info(f"MEMBERSHIP: Expiry check finished. {expired_count} users expired.")


class Bot(Client):
    def __init__(self):
        super().__init__(
            "Project-Siesta",
            api_id=Config.APP_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.TG_BOT_TOKEN,
            plugins=plugins,
            workdir=Config.WORK_DIR,
            workers=100
        )
        self.admin_ids = Config.ADMINS # Admin ID များကို သိမ်းဆည်း

    async def start(self):
        await super().start()
        # Expiry Checker ကို Background Task အဖြစ် စတင်
        self.loop.create_task(check_membership_expiry()) 
        await bot_set.login_qobuz()
        await bot_set.login_deezer()
        await bot_set.login_tidal()
        LOGGER.info("BOT : Started Successfully")

    async def stop(self, *args):
        await super().stop()
        for client in bot_set.clients:
            await client.session.close()
        LOGGER.info('BOT : Exited Successfully ! Bye..........')

aio = Bot()
