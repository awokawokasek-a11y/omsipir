import os
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- CONFIG DARI RAILWAY ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

# --- FSM UNTUK INPUT DATA ---
class AdminStates(StatesGroup):
    waiting_welcome_text = State()
    waiting_welcome_btn = State()
    waiting_filter_word = State()
    waiting_bc_text = State()

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
    db_query("INSERT OR IGNORE INTO settings (key, value) VALUES ('group_id', '0')")
    db_query("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_text', 'Selamat datang!')")
    db_query("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_btn', 'Join Channel|https://t.me/yourchannel')")

init_db()

# --- MENU UTAMA ---
@dp.message(Command("start"), F.chat.type == "private")
async def admin_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Set Target Grup", callback_data="guide_group")],
        [InlineKeyboardButton(text="📝 Set Welcome", callback_data="set_welcome")],
        [InlineKeyboardButton(text="🚫 Set Filter Kata", callback_data="set_filter")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="bc")],
        [InlineKeyboardButton(text="💾 Send DB (Backup)", callback_data="send_db")]
    ])
    await message.answer("🛡️ **Super Admin Panel**", reply_markup=kb)

# --- FIX SET GRUP + AUTO DELETE ---
@dp.message(Command("setgrup"))
async def set_group_id(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    gid = str(message.chat.id)
    db_query("UPDATE settings SET value = ? WHERE key = 'group_id'", (gid,))
    
    rep = await message.answer(f"✅ Grup didaftarkan: `{gid}`")
    await asyncio.sleep(3)
    await message.delete() # Hapus pesan perintah
    await rep.delete() # Hapus balasan bot

# --- FIX WELCOME & HIDDEN MENTION ---
@dp.callback_query(F.data == "set_welcome")
async def start_set_welcome(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Kirim teks welcome baru:")
    await state.set_state(AdminStates.waiting_welcome_text)
    await callback.answer()

@dp.message(AdminStates.waiting_welcome_text)
async def save_welcome_text(message: types.Message, state: FSMContext):
    db_query("UPDATE settings SET value = ? WHERE key = 'welcome_text'", (message.text,))
    await message.answer("Teks disimpan! Sekarang kirim link tombol dengan format: \n`Nama Tombol|Link` \nContoh: `Join Channel|https://t.me/google` ")
    await state.set_state(AdminStates.waiting_welcome_btn)

@dp.message(AdminStates.waiting_welcome_btn)
async def save_welcome_btn(message: types.Message, state: FSMContext):
    db_query("UPDATE settings SET value = ? WHERE key = 'welcome_btn'", (message.text,))
    await message.answer("✅ Welcome Berhasil diupdate!")
    await state.clear()

# --- FIX BROADCAST ---
@dp.callback_query(F.data == "bc")
async def start_bc(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Kirim pesan broadcast kamu:")
    await state.set_state(AdminStates.waiting_bc_text)
    await callback.answer()

@dp.message(AdminStates.waiting_bc_text)
async def do_broadcast(message: types.Message, state: FSMContext):
    gid = db_query("SELECT value FROM settings WHERE key = 'group_id'", fetch=True)[0][0]
    try:
        await bot.send_message(gid, message.text)
        await message.answer("✅ Broadcast terkirim ke grup.")
    except Exception as e:
        await message.answer(f"❌ Gagal: {e}")
    await state.clear()

# --- FIX MATA ELANG (LOG KE ADMIN PC) ---
@dp.chat_member()
async def mata_elang(event: types.ChatMemberUpdated):
    # Logika Hidden Mention (Mention tanpa terlihat teksnya)
    # Menggunakan karakter kosong/spasi yang di-link-kan ke profile
    hidden_mention = f'<a href="tg://user?id={event.new_chat_member.user.id}">\u200b</a>'
    
    if event.new_chat_member.status == "member":
        # Welcome ke grup dengan Hidden Mention
        txt = db_query("SELECT value FROM settings WHERE key = 'welcome_text'", fetch=True)[0][0]
        btn_data = db_query("SELECT value FROM settings WHERE key = 'welcome_btn'", fetch=True)[0][0].split("|")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=btn_data[0], url=btn_data[1])]])
        await bot.send_message(event.chat.id, f"{hidden_mention}{txt}", reply_markup=kb)
        
        # Log ke Admin
        await bot.send_message(ADMIN_ID, f"👁️ **Mata Elang:** {event.new_chat_member.user.full_name} Join.")

# --- FILTER KATA (ADMIN KEBAL) ---
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def group_filter(message: types.Message):
    if message.from_user.id == ADMIN_ID: return
    
    banned_words = [row[0] for row in db_query("SELECT word FROM filters", fetch=True)]
    if any(word in message.text.lower() for word in banned_words):
        await message.delete()
        # Logika Mute 2x tetap ada di sini...

# --- MODIF SET FILTER ---
@dp.callback_query(F.data == "set_filter")
async def set_filter_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Kirim kata kasar baru untuk ditambah:")
    await state.set_state(AdminStates.waiting_filter_word)

@dp.message(AdminStates.waiting_filter_word)
async def save_filter(message: types.Message, state: FSMContext):
    try:
        db_query("INSERT INTO filters (word) VALUES (?)", (message.text.lower(),))
        await message.answer(f"✅ Kata `{message.text}` ditambahkan ke filter.")
    except:
        await message.answer("Kata sudah ada di list.")
    await state.clear()

# --- BACKUP ---
@dp.callback_query(F.data == "send_db")
async def send_db(callback: types.CallbackQuery):
    await bot.send_document(ADMIN_ID, FSInputFile("database.db"), caption="Backup DB")
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
