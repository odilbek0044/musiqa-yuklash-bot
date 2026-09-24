import os, logging, subprocess, datetime, asyncio, html, re, requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, InlineQueryHandler
from yt_dlp import YoutubeDL
from shazamio import Shazam
import config
from flask import Flask
import threading

# ---- Render uchun web server ----
flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return "Bot ishlayapti! 🤖"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, debug=False)

threading.Thread(target=run_web, daemon=True).start()
# ---------------------------------

logging.basicConfig(level=logging.INFO)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
PER_PAGE = 6

def clean_downloads():
    try:
        for f in os.listdir(DOWNLOAD_DIR):
            fp = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(fp):
                os.remove(fp)
    except: pass

USERS_FILE = "/data/users.txt" if os.path.exists("/data") else "users.txt"

START_TEXT = f"""
🎧 <b>{{user}} uchun {config.BOT_NAME}!</b> ✨
━━━━━━━━━━━━━━━━━━━━━━
Salom, <b>{{user}}!</b> 👋

Men siz uchun:
🎬 <b>Video yuklayman MP4 da</b>
   📺 YouTube, 📸 Instagram

🎵 <b>Va avtomatik MP3 ham!</b>
   🔊 Xuddi shu videoning audiosi

🎤 <b>Golos / Video yuboring</b>
   🔍 Shazam orqali musiqasini topib beraman!

⚡ <b>Juda tez, sifatli, bepul!</b>
━━━━━━━━━━━━━━━━━━━━━━
👇 <b>Qanday ishlatiladi?</b>
1⃣ 🔗 Menga link yuboring
2⃣ 🔍 Yoki qo'shiq nomini yozing:
   <code>Alan Walker - Alone</code>
3⃣ 🎤 Golos yoki video yuboring!

Men darhol sizga <b>VIDEO + AUDIO</b> ni yuboraman! 🚀
"""

ABOUT_TEXT = """
🤖 <b>Musiqa Yuklash Bot haqida</b> ✨
━━━━━━━━━━━━━━━━━━━━━━
🎧 <b>Bu bot nima qila oladi?</b>

🎬 <b>Video Yuklash:</b>
YouTube, Instagram va boshqa platformalardan videolarni yuqori sifatda yuklab beradi!

🎵 <b>Audio Ajratish:</b>
Yuklangan videoni avtomatik ravishda MP3 formatga o'tkazib, musiqasini alohida yuboradi!

🎤 <b>Shazam Xizmati:</b>
Ovozli xabar yoki video yuborsangiz, ichidagi musiqani Shazam orqali topib, yuklab beradi!

🔍 <b>Qidiruv:</b>
Qo'shiq nomini yozing, masalan:
<code>Alan Walker - Alone</code>
Men eng yaxshi natijalarni topib beraman!

━━━━━━━━━━━━━━━━━━━━━━
⚙ <b>Texnologiyalar:</b>
Python, yt-dlp, ShazamIO, FFmpeg

👨💻 <b>Dasturchi:</b> Odilbek Axtamov
📅 <b>Ishga tushgan:</b> 2026-yil, Sentyabr
🔗 <b>Aloqa:</b> @odilbek_axtamov

Barcha huquqlar himoyalangan © 2026 🛡
"""

ADMIN_TEXT = """
👑 <b>Admin bilan bog'lanish</b>
━━━━━━━━━━━━━━━━━━━━━━
😊 Savollaringiz, takliflaringiz bo'lsa
admin bilan bog'laning:

👉 <b>@odilbek_axtamov</b> 💬

📩 24 soat ichida javob beriladi!
✉ Xabaringizni kutyapmiz!
"""

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ Bot haqida", callback_data="about"), InlineKeyboardButton("👑 Admin", callback_data="admin")],
        [InlineKeyboardButton("💡 Takliflar va tavsiyalar", callback_data="feedback")]
    ])

def is_url(text):
    return text.startswith("http://") or text.startswith("https://")

def search_youtube(query):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios'],
                'player_skip': ['webpage', 'configs']
            }
        },
        'http_headers': {
            'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 14) gzip',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch20:{query}", download=False)
        return info.get('entries', [])[:20]

def build_search_text(query, results, page):
    total_pages = (len(results) + PER_PAGE - 1) // PER_PAGE
    start = page * PER_PAGE
    end = start + PER_PAGE
    chunk = results[start:end]
    msg = f"🎉 <b>\"{html.escape(query)}\" uchun topildi:</b> 🔍\n\n"
    for idx, e in enumerate(chunk, start=start+1):
        t = e.get('title', '')[:45]
        msg += f"<b>{idx}.</b> {html.escape(t)}\n"
    msg += f"\n📄 <b>Sahifa {page+1}/{total_pages}</b>\n👇 <b>Tanlang!</b>"
    return msg, chunk

def build_search_keyboard(results, page):
    total_pages = (len(results) + PER_PAGE - 1) // PER_PAGE
    start = page * PER_PAGE
    end = start + PER_PAGE
    chunk = results[start:end]
    keyboard = []
    row = []
    for i, e in enumerate(chunk):
        global_idx = start + i + 1
        row.append(InlineKeyboardButton(f"{global_idx}", callback_data=f"dl_{e['id']}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("❤ Avvalgisi", callback_data=f"search_page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("🩷 Keyingisi", callback_data=f"search_page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    return InlineKeyboardMarkup(keyboard)

def clean_url(url):
    return url.split('&')[0].split('?si=')[0]

def get_lyrics(title):
    try:
        if " - " in title:
            artist, song = title.split(" - ", 1)
        else:
            artist = ""
            song = title
        song = re.sub(r'\[.*?\]|\(.*?\)', '', song).strip()
        artist = re.sub(r'\[.*?\]|\(.*?\)', '', artist).strip()
        if not artist:
            return None
        url = f"https://api.lyrics.ovh/v1/{artist}/{song}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            lyrics = data.get('lyrics')
            if lyrics and len(lyrics) > 20:
                return lyrics
    except Exception as e:
        logging.error(f"Lyrics xato: {e}")
    return None

def build_after_audio_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎤 So'zlari", callback_data="lyrics_yes"), InlineKeyboardButton("📹 Video", callback_data="want_video_yes")],
        [InlineKeyboardButton("🐢 Slowed + Reverb", callback_data="effect_slowed"), InlineKeyboardButton("🔊 Bass Boosted", callback_data="effect_bass")],
        [InlineKeyboardButton("🎤 Karaoke kuylamoqchimisiz?", callback_data="effect_karaoke")],
        [InlineKeyboardButton("❌ Kerak emas", callback_data="cancel_inline")]
    ])

def apply_audio_effect(input_path, effect_type):
    output_path = input_path.rsplit('.', 1)[0] + f"_{effect_type}.mp3"
    try:
        if effect_type == "slowed":
            filt = "atempo=0.85,aecho=0.8:0.88:60:0.4"
        elif effect_type == "bass":
            filt = "bass=g=12:f=110:w=0.6,equalizer=f=60:width_type=o:width=1.5:g=8"
        elif effect_type == "karaoke":
            filt = "pan=mono|c0=c0-c1,pan=stereo|c0=c0|c1=c0"
        else:
            return None
        subprocess.run(['ffmpeg','-y','-i',input_path,'-filter:a',filt,'-q:a','2',output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return output_path
    except: pass
    return None

async def download_and_send(url, context, status_msg, chat_id):
    url = clean_url(url)
    audio_path = None
    steps = [
        "🔍 <b>Musiqa tekshirilmoqda...</b> 🎧",
        "✅ <b>So'rov qabul qilindi...</b> 📩",
        "🎵 <b>Musiqangiz qidirilmoqda...</b> ⚡",
        "🚀 <b>Natija tayyorlanmoqda...</b> ✨"
    ]
    for txt in steps:
        try:
            await status_msg.edit_text(txt, parse_mode='HTML')
        except:
            pass
        await asyncio.sleep(1.5)
    formats_to_try = [
        'bestaudio[ext=m4a]/bestaudio/best',
        'bestaudio/best',
    ]
    for fmt in formats_to_try:
        try:
            await status_msg.edit_text("🎧 <b>Audio yuklanmoqda...</b> ⚡", parse_mode='HTML')
            ydl_opts = {
                'format': fmt,
                'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
                'socket_timeout': 60,
                'retries': 10,
                'fragment_retries': 10,
                'extractor_retries': 3,
                'file_access_retries': 3,
                'http_headers': {
                    'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 14) gzip',
                    'Accept-Language': 'en-US,en;q=0.9',
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['ios'],
                        'player_skip': ['webpage', 'configs'],
                    }
                },
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = info['id']
                title = info.get('title','Video')[:60]
                safe_title = html.escape(title)
                duration = info.get('duration',0)
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(video_id):
                        audio_path = os.path.join(DOWNLOAD_DIR, f)
                        break
            if not audio_path or not os.path.exists(audio_path):
                continue
            mins, secs = divmod(int(duration), 60)
            cap_a = f"🎵 <b>{safe_title}</b>"
            cap_v = f"🎵 <b>{safe_title}</b>"
            final_path = audio_path
            if not audio_path.lower().endswith('.mp3'):
                try:
                    mp3_tmp = os.path.join(DOWNLOAD_DIR, f"{video_id}_final.mp3")
                    subprocess.run(['ffmpeg','-y','-i',audio_path,'-vn','-q:a','2',mp3_tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
                    if os.path.exists(mp3_tmp) and os.path.getsize(mp3_tmp) > 1000:
                        try: os.remove(audio_path)
                        except: pass
                        final_path = mp3_tmp
                except: pass
            with open(final_path, 'rb') as audio_file:
                msg = await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=audio_file,
                    title=title,
                    caption=f"🎵 <b>{html.escape(title)}</b>",
                    parse_mode='HTML',
                    reply_markup=build_after_audio_keyboard()
                )
            try:
                if os.path.exists(final_path):
                    os.remove(final_path)
            except: pass
            for f in os.listdir(DOWNLOAD_DIR):
                if video_id in f:
                    try: os.remove(os.path.join(DOWNLOAD_DIR, f))
                    except: pass
            try: await status_msg.delete()
            except: pass
            return True, cap_v, title, url
        except Exception as e:
            logging.error(f"Download urinish xato {fmt}: {e}")
            try:
                for f in os.listdir(DOWNLOAD_DIR):
                    if video_id in f if 'video_id' in locals() else False:
                        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
                        except: pass
            except: pass
            continue
    try: await status_msg.delete()
    except: pass
    return None, None, None, url

async def handle_voice_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = await update.message.reply_text("🎧 <b>Eshitib ko'ryapman...</b> 👂✨\n🔍 <b>Musiqa qidirilmoqda...</b> 🎵", parse_mode='HTML')
    file_path = None
    mp3_path = None
    wav_path = None
    try:
        if update.message.voice:
            file = await update.message.voice.get_file()
            file_path = os.path.join(DOWNLOAD_DIR, f"voice_{file.file_id}.ogg")
        elif update.message.video:
            file = await update.message.video.get_file()
            file_path = os.path.join(DOWNLOAD_DIR, f"video_{file.file_id}.mp4")
        elif update.message.video_note:
            file = await update.message.video_note.get_file()
            file_path = os.path.join(DOWNLOAD_DIR, f"note_{file.file_id}.mp4")
        elif update.message.audio:
            file = await update.message.audio.get_file()
            file_path = os.path.join(DOWNLOAD_DIR, f"audio_{file.file_id}.mp3")
        else:
            return
        await file.download_to_drive(file_path)
        await status.edit_text("✂ <b>Videodan ovoz ajratilmoqda...</b> 🎬➡🎧", parse_mode='HTML')
        mp3_path = file_path.rsplit('.', 1)[0] + "_cut.mp3"
        try:
            subprocess.run(['ffmpeg','-y','-i',file_path,'-vn','-ar','44100','-ac','2','-q:a','0',mp3_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        except Exception as e:
            logging.error(f"ffmpeg cut xato: {e}")
        audio_ready = False
        if mp3_path and os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 2000:
            audio_ready = True
            with open(mp3_path,'rb') as af:
                await update.message.reply_audio(audio=af, caption="🎧 <b>Ovozi ajratib olindi!</b> ✨\n🔍 <b>Endi musiqa qidirilmoqda...</b> 🎵", parse_mode='HTML')
        await status.edit_text("🔍 <b>Musiqa qidirilmoqda...</b> 🎵✨", parse_mode='HTML')
        shazam_input = mp3_path if audio_ready else file_path
        wav_path = file_path.rsplit('.', 1)[0] + "_shazam.mp3"
        try:
            subprocess.run(['ffmpeg','-y','-i',shazam_input,'-ss','2','-t','12','-ar','44100','-ac','2',wav_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        except Exception as e:
            logging.error(f"ffmpeg shazam cut xato: {e}")
            wav_path = shazam_input
        shazam = Shazam()
        out = None
        if os.path.exists(wav_path):
            try:
                out = await shazam.recognize(wav_path)
            except Exception as e:
                logging.error(f"Shazam xato: {e}")
        if out and out.get('track'):
            track = out['track']
            title = track.get('title','Noma\'lum')
            artist = track.get('subtitle','Noma\'lum')
            full_name = f"{artist} - {title}"
            await status.edit_text(f"🎉 <b>Topildi🥳</b>\n🎤 <b>{html.escape(artist)}</b>\n🎵 <b>{html.escape(title)}</b>\n\n📥 <b>Yuklanmoqda...</b> 🚀", parse_mode='HTML')
            results = search_youtube(full_name)
            if results:
                url = f"https://www.youtube.com/watch?v={results[0]['id']}"
                ok, cap_v, t, video_url = await download_and_send(url, context, status, update.effective_chat.id)
                if ok:
                    context.user_data['pending_video_url'] = video_url
                    context.user_data['pending_video_caption'] = cap_v
                    context.user_data['pending_video_title'] = title
        if audio_ready:
            await status.edit_text("✅ <b>Ovoz ajratib olindi!</b> 🎧\n😔 <b>Shazam topa olmadi, qo'shiq nomini yozib yuboring!</b> 🔍", parse_mode='HTML', reply_markup=main_keyboard())
        else:
            await status.edit_text("😔 <b>Musiqa topilmadi va ovoz ham ajratilmadi...</b> 🎵\n🔊 Videoda ovoz borligiga ishonch hosil qiling!", parse_mode='HTML', reply_markup=main_keyboard())
    except Exception as e:
        logging.error(f"Shazam umumiy xato: {e}")
        await status.edit_text("😔 <b>Topilmadi, qayta urinib ko'ring!</b>", parse_mode='HTML', reply_markup=main_keyboard())
    finally:
        try:
            if file_path and os.path.exists(file_path): os.remove(file_path)
            if mp3_path and os.path.exists(mp3_path): os.remove(mp3_path)
            if wav_path and os.path.exists(wav_path) and wav_path!= mp3_path and wav_path!= file_path: os.remove(wav_path)
        except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        users_file = "/data/users.txt" if os.path.exists("/data") else "users.txt"
        is_new = True
        if os.path.exists(users_file):
            with open(users_file, "r", encoding="utf-8") as f:
                if str(user.id) in f.read():
                    is_new = False
        if is_new:
            with open(users_file, "a", encoding="utf-8") as f:
                f.write(f"{user.id}\n")
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_text = (f"🆕 <b>YANGI USER START BOSDI! 🚀</b>\n👤 <b>Ism:</b> {user.first_name}\n🔗 <b>Username:</b> @{user.username or 'yoq'}\n🆔 <b>ID:</b> <code>{user.id}</code>\n⏰ <b>Vaqt:</b> {now}\n")
            await context.bot.send_message(chat_id=config.ADMIN_ID, text=log_text, parse_mode='HTML')
    except Exception as e:
        logging.error(f"new user log xato: {e}")
    context.user_data['awaiting_feedback'] = False
    text = START_TEXT.format(user=user.first_name)
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=main_keyboard())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_admin_reply'):
        user = update.effective_user
        user_text = update.message.text
        log_to_admin = (
            f"💬 <b>User javob berdi!</b>\n"
            f"━━━━━━━━━━━━\n"
            f"👤 {user.first_name} (@{user.username})\n"
            f"🆔 <code>{user.id}</code>\n"
            f"💌 Javobi:\n{html.escape(user_text)}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✉ Javob berish", callback_data=f"admin_reply_{user.id}")]
        ])
        await context.bot.send_message(chat_id=config.ADMIN_ID, text=log_to_admin, parse_mode='HTML', reply_markup=keyboard)
        thank_msg = await update.message.reply_text("✅ <b>Javobingiz uchun rahmat! Admin ko'radi.</b>", parse_mode='HTML')
        try:
            await asyncio.sleep(3)
            await context.bot.delete_message(chat_id=context.user_data['admin_chat_id'], message_id=context.user_data['admin_msg_id'])
            await context.bot.delete_message(chat_id=context.user_data['admin_chat_id'], message_id=context.user_data['prompt_msg_id'])
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=thank_msg.message_id)
        except:
            pass
        context.user_data['awaiting_admin_reply'] = False
        return
    if context.user_data.get('awaiting_admin_to_user'):
        target_id = context.user_data['awaiting_admin_to_user']
        text, kb = build_admin_message(update.message.text)
        try:
            await context.bot.send_message(chat_id=target_id, text=text, parse_mode='HTML', reply_markup=kb)
            await update.message.reply_text(f"✅ {target_id} ga yuborildi!")
        except Exception as e:
            await update.message.reply_text(f"❌ Xato: {e}")
        context.user_data['awaiting_admin_to_user'] = None
        return
    txt = update.message.text.strip()
    if context.user_data.get('awaiting_feedback'):
        context.user_data['awaiting_feedback'] = False
        user = update.message.from_user
        fwd = f"💡 <b>YANGI TAKLIF!</b>\n👤 {user.first_name} (@{user.username or 'yoq'})\n🆔 <code>{user.id}</code>\n✉ {txt}"
        try: await context.bot.send_message(chat_id=config.ADMIN_ID, text=fwd, parse_mode='HTML')
        except: pass
        await update.message.reply_text("✅ <b>Rahmat! Xabaringiz yuborildi!</b>", parse_mode='HTML', reply_markup=main_keyboard())
        return

    if is_url(txt):
        if "tiktok.com" in txt:
            await update.message.reply_text("🚫 <b>TikTok o'chirilgan!</b>", parse_mode='HTML', reply_markup=main_keyboard())
            return
        status = await update.message.reply_text("⏳ <b>Boshlanmoqda...</b> ✨", parse_mode='HTML')
        ok, cap_v, title, video_url = await download_and_send(txt, context, status, update.effective_chat.id)
        if ok:
            context.user_data['pending_video_url'] = video_url
            context.user_data['pending_video_caption'] = cap_v
            context.user_data['pending_video_title'] = title
    else:
        status = await update.message.reply_text(f"🔍 <b>\"{html.escape(txt)}\" qidirilmoqda...</b> 🎵✨", parse_mode='HTML')
        results = search_youtube(txt)
        if not results:
            await status.edit_text("❌ Topilmadi! Qayta urinib ko'ring 😔")
            return
        context.user_data['last_search_results'] = results
        context.user_data['last_search_query'] = txt
        context.user_data['last_search_page'] = 0
        text, _ = build_search_text(txt, results, 0)
        kb = build_search_keyboard(results, 0)
        await status.edit_text(text, parse_mode='HTML', reply_markup=kb)

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.inline_query.query.strip()
    if not q or len(q) < 2:
        return
    try:
        results = search_youtube(q)
        articles = []
        for r in results[:10]:
            vid = r['id']
            title = r.get('title', 'Noma\'lum')[:60]
            url = f"https://www.youtube.com/watch?v={vid}"
            channel = r.get('uploader', 'YouTube')
            articles.append(
                InlineQueryResultArticle(
                    id=vid,
                    title=title,
                    description=f"🎵 {channel} | Bosing va yuboring!",
                    input_message_content=InputTextMessageContent(
                        message_text=f"🎵 <b>{html.escape(title)}</b>\n\n🔗 {url}\n\n🤖 @{context.bot.username} orqali yuklandi! 🚀",
                        parse_mode='HTML'
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎧 MP3 ni Yuklash",
                                              url=f"https://t.me/{context.bot.username}?start={vid}")]
                    ])
                )
            )
        await update.inline_query.answer(articles, cache_time=0)
    except Exception as e:
        logging.error(f"Inline xato: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    if query.data == "reply_to_admin":
        prompt_msg = await query.message.reply_text("✍ <b>Javobingizni yozing:</b>\nAdmin sizga javob beradi!", parse_mode='HTML')
        context.user_data['awaiting_admin_reply'] = True
        context.user_data['admin_msg_id'] = query.message.message_id
        context.user_data['prompt_msg_id'] = prompt_msg.message_id
        context.user_data['admin_chat_id'] = query.message.chat_id
        return

    if query.data.startswith("admin_reply_"):
        target_id = int(query.data.split("_")[-1])
        context.user_data['awaiting_admin_to_user'] = target_id
        await context.bot.send_message(chat_id=config.ADMIN_ID, text=f"✍ <b>{target_id} ga javobingizni yozing:</b>", parse_mode='HTML')
        return

    if query.data.startswith("search_page_"):
        try:
            page = int(query.data.split("_")[-1])
            results = context.user_data.get('last_search_results', [])
            qtxt = context.user_data.get('last_search_query', '')
            if not results: return
            context.user_data['last_search_page'] = page
            text, _ = build_search_text(qtxt, results, page)
            kb = build_search_keyboard(results, page)
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=kb)
        except: pass
        return

    if query.data == "about":
        await context.bot.send_message(chat_id=chat_id, text=ABOUT_TEXT, parse_mode='HTML', reply_markup=main_keyboard())
    elif query.data == "admin":
        await context.bot.send_message(chat_id=chat_id, text=ADMIN_TEXT, parse_mode='HTML', reply_markup=main_keyboard())
    elif query.data == "feedback":
        context.user_data['awaiting_feedback'] = True
        await context.bot.send_message(chat_id=chat_id, text="💡 <b>Takliflar va tavsiyalar ✨</b>\n\n✍ <b>Xabaringizni yozing:</b> 💬", parse_mode='HTML')
    elif query.data.startswith("dl_"):
        url = f"https://www.youtube.com/watch?v={query.data[3:]}"
        status = await context.bot.send_message(chat_id=chat_id, text="⏳ <b>Yuklanmoqda...</b> ✨", parse_mode='HTML')
        ok, cap_v, title, video_url = await download_and_send(url, context, status, chat_id)
        if ok:
            context.user_data['pending_video_url'] = video_url
            context.user_data['pending_video_caption'] = cap_v
            context.user_data['pending_video_title'] = title
    elif query.data == "cancel_inline":
        try: await query.edit_message_reply_markup(reply_markup=None)
        except: pass
    elif query.data == "lyrics_yes":
        title = context.user_data.get('pending_video_title', 'Video')
        status_lyrics = await context.bot.send_message(chat_id=chat_id, text=f"🎤 <b>{html.escape(title)}</b> uchun so'zlar qidirilmoqda... 📜✨", parse_mode='HTML')
        lyrics = get_lyrics(title)
        try: await status_lyrics.delete()
        except: pass
        if lyrics:
            pretty = f"🎤 <b>{html.escape(title)}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n<pre>{html.escape(lyrics[:3500])}</pre>\n━━━━━━━━━━━━━━━━━━━━━━\n🤖 @{context.bot.username}"
            await context.bot.send_message(chat_id=chat_id, text=pretty, parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"😔 <b>{html.escape(title)}</b> uchun so'zlar topilmadi... 🥲", parse_mode='HTML', reply_markup=main_keyboard())
    elif query.data == "want_video_yes":
        url = context.user_data.get('pending_video_url')
        if not url:
            await query.message.reply_text("😔 Avval musiqa yuboring, keyin video bosing!")
            return
        status = await context.bot.send_message(chat_id=chat_id, text="📹 <b>Video yuklanmoqda...</b> 🎬", parse_mode='HTML')
        ydl_opts = {
            'format': 'bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'quiet': True,
            'noplaylist': True,
            'merge_output_format': 'mp4',
            'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'socket_timeout': 60,
            'retries': 10,
            'fragment_retries': 10,
            'extractor_retries': 3,
            'http_headers': {
                'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 14) gzip',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'mweb', 'web_safari', 'tv_embedded'],
                    'player_skip': ['webpage', 'configs'],
                }
            }
        }
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = info['id']
                video_path = None
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(video_id) and f.endswith(('.mp4', '.mkv', '.webm')):
                        video_path = os.path.join(DOWNLOAD_DIR, f)
                        break
            if video_path and os.path.exists(video_path):
                with open(video_path, 'rb') as v:
                    await context.bot.send_video(chat_id=chat_id, video=v, caption=f"🎵 <b>{html.escape(context.user_data.get('pending_video_title',''))}</b>", parse_mode='HTML', reply_markup=build_after_audio_keyboard())
                try: os.remove(video_path)
                except: pass
        except Exception as e:
            logging.error(f"Video xato: {e}")
        try: await status.delete()
        except: pass
    elif query.data.startswith("effect_"):
        effect = query.data.split("_")[1]
        title = context.user_data.get('pending_video_title', 'Audio'); url = context.user_data.get('pending_video_url')
        if not url: await context.bot.send_message(chat_id=chat_id, text="😔 <b>Asl musiqa topilmadi!</b>", parse_mode='HTML'); return
        status_eff = await context.bot.send_message(chat_id=chat_id, text=f"✨ Effekt qilinmoqda...", parse_mode='HTML')
        tmp_path = None; eff_path = None
        try:
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
                'quiet': True,
                'noplaylist': True,
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
                'socket_timeout': 60,
                'retries': 10,
                'fragment_retries': 10,
                'extractor_retries': 3,
                'http_headers': {
                    'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 14) gzip',
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios', 'mweb', 'web_safari', 'tv_embedded'],
                        'player_skip': ['webpage', 'configs'],
                    }
                }
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True); vid = info['id']
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(vid): tmp_path = os.path.join(DOWNLOAD_DIR, f); break
            if tmp_path:
                eff_path = apply_audio_effect(tmp_path, effect)
                if eff_path:
                    with open(eff_path,'rb') as ef:
                        await context.bot.send_audio(chat_id=chat_id, audio=ef, title=f"{title} ({effect})", caption=f"🎵 <b>{html.escape(title)}</b>", parse_mode='HTML', reply_markup=build_after_audio_keyboard())
        finally:
            try: await status_eff.delete()
            except: pass
            if tmp_path and os.path.exists(tmp_path): os.remove(tmp_path)
            if eff_path and os.path.exists(eff_path): os.remove(eff_path)

def build_admin_message(admin_text):
    safe_text = html.escape(admin_text)
    text = (
        f"📩 <b>👑 Admindan xabar keldi!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<tg-spoiler>{safe_text}</tg-spoiler>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👆 Xabarni o'qish uchun spoylerni bosing!"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Javob berish", callback_data="reply_to_admin")]
    ])
    return text, keyboard

async def broadcast(update: Update, context):
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("⛔ Siz admin emassiz!") # update.message
        return

    if update.message.reply_to_message:
        admin_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    else:
        if not context.args:
            await update.message.reply_text("📢 Foydalanish: <code>/broadcast Salom!</code>\nYoki xabarga reply qilib /broadcast yozing", parse_mode='HTML')
            return
        admin_text = " ".join(context.args)

    users_file = "/data/users.txt" if os.path.exists("/data") else "users.txt"
    if not os.path.exists(users_file):
        await update.message.reply_text("😔 Hali user yo'q! users.txt topilmadi")
        return

    with open(users_file, "r", encoding="utf-8") as f:
        users = [int(line.strip()) for line in f if line.strip().isdigit()]

    if not users:
        await update.message.reply_text("😔 Userlar ro'yxati bo'sh!")
        return

    text, keyboard = build_admin_message(admin_text)
    status = await update.message.reply_text(f"🚀 {len(users)} ta userga yuborilmoqda... 0/{len(users)}", parse_mode='HTML')

    success = 0
    blocked = 0

    for idx, uid in enumerate(users, 1):
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode='HTML', reply_markup=keyboard)
            success += 1
        except Exception as e:
            if "blocked" in str(e).lower() or "not found" in str(e).lower():
                blocked += 1
            logging.warning(f"Broadcast xato {uid}: {e}")

        if idx % 5 == 0:
            try:
                await status.edit_text(f"🚀 Yuborilmoqda... {idx}/{len(users)}\n✅ Yuborildi: {success}\n🚫 Block: {blocked}", parse_mode='HTML')
            except:
                pass
        await asyncio.sleep(0.07)

    await status.edit_text(f"✅ <b>Broadcast tugadi!</b>\n\n📊 Jami: {len(users)} ta\n✅ Yuborildi: {success} ta\n🚫 Blocklagan: {blocked} ta", parse_mode='HTML')

async def send_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= config.ADMIN_ID:
        return
    if len(context.args) < 1:
        await update.message.reply_text("Foydalanish: /send 123456789 Salom!", parse_mode='HTML')
        return
    try:
        target_id = int(context.args[0])
        if update.message.reply_to_message:
            admin_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or "Xabar"
        else:
            admin_text = " ".join(context.args[1:])
        text, keyboard = build_admin_message(admin_text)
        await context.bot.send_message(chat_id=target_id, text=text, parse_mode='HTML', reply_markup=keyboard)
        await update.message.reply_text(f"✅ {target_id} ga yuborildi!")
    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= config.ADMIN_ID:
        await update.message.reply_text("⛔ Siz admin emassiz!")
        return
    total = 0
    users_file = "/data/users.txt" if os.path.exists("/data") else "users.txt"
    if os.path.exists(users_file):
        with open(users_file, "r", encoding="utf-8") as f:
            total = len([line for line in f if line.strip().isdigit()])
    size_kb = 0
    if os.path.exists(users_file):
        size_kb = os.path.getsize(users_file) / 1024
    text = (
        f"📊 <b>Bot Statistikasi</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Jami userlar:</b> {total} ta\n"
        f"📁 <b>Baza hajmi:</b> {size_kb:.1f} KB\n"
        f"🤖 <b>Bot:</b> @{context.bot.username}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Bot aktiv ishlayapti!"
    )
    await update.message.reply_text(text, parse_mode='HTML')

def main():
    clean_downloads()
    print(f"🤖 {config.BOT_NAME} ishga tushdi... ✨")
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("send", send_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("stat", stats_cmd))
    app.add_handler(CommandHandler("users", stats_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.VIDEO | filters.VIDEO_NOTE | filters.AUDIO, handle_voice_video))
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
