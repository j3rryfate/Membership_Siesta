import psycopg2
import datetime
import psycopg2.extras
from .pg_db import DataBaseHandle
import json

from config import Config
from bot.logger import LOGGER

#special_characters = ['!','#','$','%', '&','@','[',']',' ',']','_', ',', '.', ':', ';', '<', '>', '?', '\\', '^', '`', '{', '|', '}', '~']

"""
SETTINGS VARS

AUTH_CHATS - Chats where bot is allowed (str)
AUTH_USERS - Users who can use bot (str)
UPLOAD_MODE - RCLONE|Telegram|Local (str)
ANTI_SPAM - OFF|CHAT+|USER (str)
BOT_PUBLIC - True|False (bool)
BOT_LANGUAGE - (str) ISO 639-1 Codes Only
ART_POSTER - True|False (bool)
RCLONE_LINK_OPTIONS - False|RCLONE|Index|Both (str)
PLAYLIST_SORT - (bool)
ARTIST_BATCH_UPLOAD - (bool)
PLAYLIST_CONCURRENT - (bool)
PLAYLIST_LINK_DISABLE - Disable links for sorted playlist (bool)
ALBUM_ZIP
PLAYLIST_ZIP
ARTIST_ZIP

QOBUZ_QUALITY - (int)

TIDAL_AUTH_DATA - (blob) Tidal session saved
TIDAL_QUALITY - (str)
TIDAL_SPATIAL - (str)
"""

class UserDB(DataBaseHandle):
    def __init__(self, dburl=None):
        if dburl is None:
            dburl = Config.DATABASE_URL
        super().__init__(dburl)
        self.ensure_tables()

    def ensure_tables(self):
        """USERS table ကို စစ်ဆေးပြီး လိုအပ်သော columns များ ထည့်သွင်းခြင်း (Migration)
           PENDING_APPROVAL table ကို တည်ဆောက်ခြင်း
        """
        cur = self.scur()
        
        # 1. USERS Table Migration
        try:
            cur.execute("""
                ALTER TABLE USERS ADD COLUMN IF NOT EXISTS is_member BOOLEAN DEFAULT FALSE;
                ALTER TABLE USERS ADD COLUMN IF NOT EXISTS expiry_date TIMESTAMP;
                ALTER TABLE USERS ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE;
            """)
            
            LOGGER.info("DB: USERS table migration completed.")
        except Exception as e:
            LOGGER.error(f"DB: USERS table migration failed: {e}")
        
        # 2. PENDING_APPROVAL Table Creation
        pending_schema = """
            CREATE TABLE IF NOT EXISTS PENDING_APPROVAL (
                user_id BIGINT PRIMARY KEY NOT NULL,
                username TEXT,
                proof_chat_id BIGINT NOT NULL,
                proof_message_id INT NOT NULL,
                submitted_at TIMESTAMP NOT NULL
            )
        """
        try:
            cur.execute(pending_schema)
            LOGGER.info("DB: PENDING_APPROVAL table created/verified.")
        except Exception as e:
            LOGGER.error(f"DB: PENDING_APPROVAL table creation failed: {e}")

        self._conn.commit()
        self.ccur(cur)

    def get_user_status(self, user_id):
        """User ၏ membership နှင့် banned status ကို ရယူသည်။"""
        sql = "SELECT is_member, expiry_date, is_banned, username FROM USERS WHERE user_id=%s"
        cur = self.scur(dictcur=True)
        cur.execute(sql, (user_id,))
        row = cur.fetchone()
        self.ccur(cur)
        return row

    def ensure_user_exists(self, user_id, username=None):
        """User DB ထဲမှာ မရှိသေးရင် အသစ်ထည့်သွင်းသည်။"""
        sql = "SELECT user_id FROM USERS WHERE user_id=%s"
        cur = self.scur()
        cur.execute(sql, (user_id,))
        
        if cur.rowcount == 0:
            insert_sql = "INSERT INTO USERS (user_id, username, is_member, is_banned) VALUES (%s, %s, FALSE, FALSE)"
            cur.execute(insert_sql, (user_id, username))
            LOGGER.info(f"DB: New user {user_id} added.")

        self.ccur(cur)

    def update_user_membership(self, user_id, days: int):
        """User ကို member အဖြစ်သတ်မှတ်ပြီး သက်တမ်းထပ်တိုးသည်။ (Extend Logic)"""
        
        cur = self.scur(dictcur=True)
        # လက်ရှိ သက်တမ်းကုန်ဆုံးရက်ကို ရယူ
        current_expiry_data = self.get_user_status(user_id)

        # ရက်ပေါင်းထည့်မည့် စမှတ်ကို တွက်ချက်
        new_expiry = datetime.datetime.now() + datetime.timedelta(days=days)
        if current_expiry_data and current_expiry_data['expiry_date']:
            current_expiry = current_expiry_data['expiry_date']
            # သက်တမ်းကုန်ဆုံးရက်က အနာဂတ်မှာရှိနေသေးရင် အဲဒီရက်ကနေစပြီး ရက်ထပ်ပေါင်းမယ်
            if current_expiry > datetime.datetime.now():
                new_expiry = current_expiry + datetime.timedelta(days=days)
            # else: သက်တမ်းကုန်နေပြီဆိုရင်တော့ ဒီနေ့ကနေစပြီး ရက်ထပ်ပေါင်းမယ် (အထက်ပါအတိုင်း)
        
        # DB ထဲ Update လုပ်ခြင်း
        sql = "UPDATE USERS SET is_member=TRUE, is_banned=FALSE, expiry_date=%s WHERE user_id=%s"
        cur.execute(sql, (new_expiry, user_id))
        self._conn.commit()
        self.ccur(cur)
        return new_expiry

    def set_user_banned_status(self, user_id, is_banned: bool):
        """User ကို ban/unban လုပ်သည်။"""
        sql = "UPDATE USERS SET is_banned=%s WHERE user_id=%s"
        cur = self.scur()
        cur.execute(sql, (is_banned, user_id))
        self._conn.commit()
        self.ccur(cur)

    def get_all_users(self):
        """Broadcast အတွက် user ID အားလုံး ရယူသည်။"""
        sql = "SELECT user_id FROM USERS"
        cur = self.scur()
        cur.execute(sql)
        users = [row[0] for row in cur.fetchall()]
        self.ccur(cur)
        return users

    # --- PENDING APPROVAL FUNCTIONS ---

    def add_pending_approval(self, user_id, username, proof_chat_id, proof_message_id):
        """ငွေပေးချေမှုအထောက်အထားကို သိမ်းသည်။"""
        sql = """
            INSERT INTO PENDING_APPROVAL (user_id, username, proof_chat_id, proof_message_id, submitted_at) 
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET username = EXCLUDED.username, proof_chat_id = EXCLUDED.proof_chat_id, 
                proof_message_id = EXCLUDED.proof_message_id, submitted_at = EXCLUDED.submitted_at;
        """
        cur = self.scur()
        cur.execute(sql, (user_id, username, proof_chat_id, proof_message_id, datetime.datetime.now()))
        self._conn.commit()
        self.ccur(cur)
        
    def get_all_pending_approvals(self):
        """Admin အတွက် pending list အားလုံး ရယူသည်။"""
        sql = "SELECT user_id, username, proof_chat_id, proof_message_id, submitted_at FROM PENDING_APPROVAL ORDER BY submitted_at ASC"
        cur = self.scur(dictcur=True)
        cur.execute(sql)
        rows = cur.fetchall()
        self.ccur(cur)
        return rows

    def remove_pending(self, user_id):
        """Pending list မှ ဖယ်ရှားသည်။"""
        sql = "DELETE FROM PENDING_APPROVAL WHERE user_id=%s"
        cur = self.scur()
        cur.execute(sql, (user_id,))
        self._conn.commit()
        self.ccur(cur)
        
    def set_expired(self, user_id):
        """သက်တမ်းကုန်ဆုံးသည့် user ကို is_member=FALSE ပြန်လုပ်ပေးသည်။"""
        sql = "UPDATE USERS SET is_member=FALSE WHERE user_id=%s"
        cur = self.scur()
        cur.execute(sql, (user_id,))
        self._conn.commit()
        self.ccur(cur)
        

user_db = UserDB()


class BotSettings(DataBaseHandle):

    def __init__(self, dburl=None):
        if dburl is None:
            dburl = Config.DATABASE_URL
        super().__init__(dburl)

        settings_schema = """CREATE TABLE IF NOT EXISTS bot_settings (
            id SERIAL PRIMARY KEY NOT NULL,
            var_name VARCHAR(50) NOT NULL UNIQUE,
            var_value VARCHAR(2000) DEFAULT NULL,
            vtype VARCHAR(20) DEFAULT NULL,
            blob_val BYTEA DEFAULT NULL,
            date_changed TIMESTAMP NOT NULL
        )"""

        cur = self.scur()
        try:
            cur.execute(settings_schema)
        except psycopg2.errors.UniqueViolation:
            pass

        self._conn.commit()
        self.ccur(cur)

    def set_variable(self, var_name, var_value, update_blob=False, blob_val=None):
        vtype = "str"
        if isinstance(var_value, bool):
            vtype = "bool"
        elif isinstance(var_value, int):
            vtype = "int"

        if update_blob:
            vtype = "blob"

        sql = "SELECT * FROM bot_settings WHERE var_name=%s"
        cur = self.scur()

        cur.execute(sql, (var_name,))
        if cur.rowcount > 0:
            if not update_blob:
                sql = "UPDATE bot_settings SET var_value=%s , vtype=%s WHERE var_name=%s"
            else:
                sql = "UPDATE bot_settings SET blob_val=%s , vtype=%s WHERE var_name=%s"
                var_value = blob_val

            cur.execute(sql, (var_value, vtype, var_name))
        else:
            if not update_blob:
                sql = "INSERT INTO bot_settings(var_name,var_value,date_changed,vtype) VALUES(%s,%s,%s,%s)"
            else:
                sql = "INSERT INTO bot_settings(var_name,blob_val,date_changed,vtype) VALUES(%s,%s,%s,%s)"
                var_value = blob_val

            cur.execute(sql, (var_name, var_value, datetime.datetime.now(), vtype))

        self.ccur(cur)

    def get_variable(self, var_name):
        sql = "SELECT * FROM bot_settings WHERE var_name=%s"
        cur = self.scur()

        cur.execute(sql, (var_name,))
        if cur.rowcount > 0:
            row = cur.fetchone()
            vtype = row[3]
            val = row[2]
            if vtype == "int":
                val = int(row[2])
            elif vtype == "str":
                val = str(row[2])
            elif vtype == "bool":
                if row[2] == "true":
                    val = True
                else:
                    val = False

            return val, row[4]
        else:
            return None, None

        self.ccur(cur)

    def __del__(self):
        super().__del__()


set_db = BotSettings()
