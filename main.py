import os
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.exceptions import TelegramBadRequest

# --- CONFIG DARI RAILWAY ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- DATABASE SYSTEM ---
def db_query(query, params=(), fetch=False):
    conn = sqlite3.connect("database.db")
    curr = conn.cursor()
    curr.execute(query, params)
    data = curr.fetchall() if fetch else None
    conn.commit()
    conn.close()
    return data

def init_db():
    db_query("CREATE TABLE IF NOT EXISTS filters (word TEXT UNIQUE)")
    db_query("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    # Default settings
    db_query("INSERT OR IGNORE INTO settings (key, value) VALUES ('group_id', '0')")
    db_query("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', 'Halo selamat datang!')")

init_db()

# --- MIDDLEWARE & HELPER ---
async def is_admin(user_id):
    return user_id == ADMIN_ID

# --- MENU UTAMA (PRIVATE CHAT) ---
@dp.message(Command("start"), F.chat.type == "private")
async def admin_menu(message: types.Message):
    if not await is_admin(message.from_user.id): return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Set Target Grup", callback_data="guide_group")],
        [InlineKeyboardButton(text="📝 Set Welcome & Tombol", callback_data="set_welcome")],
        [InlineKeyboardButton(text="🚫 Set Filter Kata", callback_data="set_filter")],
        [InlineKeyboardButton(text="👁️ Mata Elang (Logs)", callback_data="view_logs")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="bc")],
        [InlineKeyboardButton(text="💾 Send DB (Backup)", callback_data="send_db")]
    ])
    await message.answer("🛡️ **Admin Control Panel**\nSemua pengaturan grup dilakukan di sini.", reply_markup=kb)

# --- SET GRUP (LOGIKA BARU) ---
@dp.callback_query(F.data == "guide_group")
async def guide_group(callback: types.CallbackQuery):
    await callback.message.answer("Caranya:\n1. Masukkan bot ke grup.\n2. Jadikan admin.\n3. Ketik `/setgrup` di dalam grup tersebut.")
    await callback.answer()

@dp.message(Command("setgrup"))
async def set_group_id(message: types.Message):
    if not await is_admin(message.from_user.id): return
    gid = str(message.chat.id)
    db_query("UPDATE settings SET value = ? WHERE key = 'group_id'", (gid,))
    await message.answer(f"✅ Grup berhasil didaftarkan!\nID: `{gid}`")

# --- FILTER KATA ---
@dp.callback_query(F.data == "set_filter")
async def menu_filter(callback: types.CallbackQuery):
    await callback.message.answer("Kirim kata yang ingin difilter (contoh: anjing, babi).")
    # Logika input kata bisa dikembangkan dengan FSMContext
    await callback.answer()

# --- MATA ELANG (LOG CHANGES) ---
@dp.chat_member()
async def mata_elang(event: types.ChatMemberUpdated):
    target_group = db_query("SELECT value FROM settings WHERE key = 'group_id'", fetch=True)[0][0]
    if str(event.chat.id) != target_group: return

    log_msg = ""
    if event.new_chat_member.status == "member":
        log_msg = f"📥 **Join:** {event.new_chat_member.user.full_name} (@{event.new_chat_member.user.username})"
    elif event.new_chat_member.status == "left":
        log_msg = f"📤 **Out:** {event.old_chat_member.user.full_name}"
    
    if log_msg:
        await bot.send_message(ADMIN_ID, log_msg)

# --- ENGINE PENGAWAS (FILTER & ANTI-SPAM) ---
warn_dict = {}

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_monitor(message: types.Message):
    target_group = db_query("SELECT value FROM settings WHERE key = 'group_id'", fetch=True)[0][0]
    if str(message.chat.id) != target_group: return

    # Admin & Bot Kebal
    member = await message.chat.get_member(message.from_user.id)
    if member.status in ["creator", "administrator"]: return

    # Pengecekan Filter
    banned_words = [row[0] for row in db_query("SELECT word FROM filters", fetch=True)]
    if any(w in message.text.lower() for w in banned_words):
        uid = message.from_user.id
        warn_dict[uid] = warn_dict.get(uid, 0) + 1
        await message.delete()
        
        if warn_dict[uid] >= 2:
            await message.chat.restrict(uid, permissions=types.ChatPermissions(can_send_messages=False))
            await message.answer(f"🔇 {message.from_user.mention_html()} di-mute (2x melanggar filter).")
        else:
            await message.answer(f"⚠️ {message.from_user.mention_html()}, jangan bicara kasar! (1/2)")

# --- BACKUP DB ---
@dp.callback_query(F.data == "send_db")
async def send_db(callback: types.CallbackQuery):
    file = FSInputFile("database.db")
    await bot.send_document(ADMIN_ID, file, caption="Backup Database")
    await callback.answer("Database dikirim!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
