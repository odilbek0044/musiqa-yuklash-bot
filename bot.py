import os, logging, subprocess, datetime, asyncio, html, re, requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, InlineQueryHandler
from yt_dlp import YoutubeDL
from shazamio import Shazam
import config

logging.basicConfig(level=logging.INFO)
DOWNLOAD_DIR = "/data/downloads"
USERS_FILE = "/data/users.txt"
TOP_FILE = "/data/top.txt"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

START_TEXT = """
🎧 <b>{user} uchun """ + config.BOT_NAME + """!</b> ✨
━━━━━━━━━━━━━━━━━━━━━━
Salom, <b>{user}!</b> 👋
🎬 <b>Video yuklayman MP4 da</b> 📺 YouTube, 📸 Instagram
🎵 <b>Va avtomatik MP3 ham!</b>
🎤 <b>Golos / Video yuboring</b> 🔍 Shazam orqali topaman!
🏆 /top - TOP 20 trend
"""

ABOUT_TEXT = """
🤖 <b>Bot Haqida ℹ</b>
💻 <b>Dasturchi:</b> Odilbek Axtamov
🚀 Musiqa Yuklash Bot 🎧
"""

ADMIN_TEXT = "👑 <b>Admin:</b> @odilbek_axtamov 💬"

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ Bot haqida", callback_data="about"), InlineKeyboardButton("👑 Admin", callback_data="admin")],
        [InlineKeyboardButton("💡 Takliflar", callback_data="feedback")]
    ])

def is_url(text):
    return text.startswith("http://") or text.startswith("https://")

def is_instagram_url(url):
    return "instagram.com" in url or "instagr.am" in url

def is_youtube_url(url):
    return "youtube.com" in url or "youtu.be" in url

def get_ydl_opts_for_search():
    opts = {
        'quiet': True, 'no_warnings': True, 'extract_flat': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'ios'], 'player_skip': ['webpage']}}
    }
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    return opts

def get_ydl_opts(url, audio_only=True):
    base = {
        'quiet': True, 'no_warnings': True, 'noplaylist': True,
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
        'socket_timeout': 30, 'retries': 10,
    }
    if is_youtube_url(url):
        base['extractor_args'] = {
            'youtube': {
                'player_client': ['android', 'ios', 'mweb', 'tv'],
                'player_skip': ['webpage', 'configs']
            }
        }
    else:
        if os.path.exists('cookies.txt'):
            base['cookiefile'] = 'cookies.txt'
        base['extractor_args'] = {'youtube': {'player_client': ['android', 'ios'], 'player_skip': ['webpage']}}
    if audio_only:
        base['format'] = 'bestaudio/best'
    else:
        base['format'] = 'bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b'
        base['merge_output_format'] = 'mp4'
    return base

def search_youtube(query):
    with YoutubeDL(get_ydl_opts_for_search()) as ydl:
        info = ydl.extract_info(f"ytsearch20:{query}", download=False)
        return info.get('entries', [])[:20]

PER_PAGE = 6

def build_search_text(query, results, page):
    total_pages = (len(results) + PER_PAGE - 1) // PER_PAGE
    start = page * PER_PAGE
    end = start + PER_PAGE
    chunk = results[start:end]
    msg = f'🎉 <b>"{html.escape(query)}" uchun topildi:</b> 🔍\n\n'
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

def build_user_video_keyboard(file_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎧 Audiosini ajratish", callback_data=f"uv_cut_{file_id}"),
         InlineKeyboardButton("🔍 Musiqani qidirish", callback_data=f"uv_shazam_{file_id}")],
        [InlineKeyboardButton("❌ Bekor qilish", callback_data=f"uv_cancel_{file_id}")]
    ])

def build_link_video_keyboard(video_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Musiqani qidirish", callback_data=f"lv_search_{video_id}")],
        [InlineKeyboardButton("✂ Audioni qirqish", callback_data=f"lv_cut_{video_id}")],
        [InlineKeyboardButton("❌ Kerak emas", callback_data=f"lv_no_{video_id}")]
    ])

def build_after_audio_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎤 So'zlari", callback_data="lyrics_yes"), InlineKeyboardButton("📹 Video", callback_data="want_video_yes")],
        [InlineKeyboardButton("🐢 Slowed version", callback_data="effect_slowed"), InlineKeyboardButton("🔊 Bass boosted", callback_data="effect_bass")],
        [InlineKeyboardButton("🎤 Karaoke kuylash", callback_data="effect_karaoke")],
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
    steps = ["✅ <b>So'rov qabul qilindi...</b>", "🔍 <b>Musiqa qidirilmoqda...</b>", "🩷 <b>Natija yuklanmoqda...</b>"]
    for txt in steps:
        try:
            await status_msg.edit_text(txt, parse_mode='HTML')
        except: pass
        await asyncio.sleep(0.7)
    formats_to_try = ['bestaudio/best', 'best']
    for fmt in formats_to_try:
        try:
            await status_msg.edit_text("🎧 <b>Audio yuklanmoqda...</b> ⚡", parse_mode='HTML')
            ydl_opts = get_ydl_opts(url, audio_only=True)
            ydl_opts['format'] = fmt
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_id = info['id']
                title = info.get('title','Video')[:60]
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(video_id):
                        audio_path = os.path.join(DOWNLOAD_DIR, f)
                        break
            if not audio_path or not os.path.exists(audio_path):
                continue
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
            await context.bot.send_audio(
                chat_id=chat_id,
                audio=open(final_path, 'rb'),
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
            try:
                with open(TOP_FILE, "a", encoding="utf-8") as tf:
                    tf.write(f"{title}\n")
            except: pass
            return True, f"🎵 <b>{html.escape(title)}</b>", title, url
        except Exception as e:
            logging.error(f"Download xato {fmt}: {e}")
            continue
    try:
        await status_msg.edit_text("❌ <b>Bu video mavjud emas!</b> 😔", parse_mode='HTML')
        await asyncio.sleep(3)
        await status_msg.delete()
    except: pass
    return None, None, None, url

async def download_and_send_video(url, context, status_msg, chat_id):
    url = clean_url(url)
    try:
        await status_msg.edit_text("✅ <b>So'rov qabul qilindi...</b>", parse_mode='HTML')
        await asyncio.sleep(0.5)
        await status_msg.edit_text("📹 <b>Video yuklanmoqda...</b> 🎬✨", parse_mode='HTML')
        ydl_opts = get_ydl_opts(url, audio_only=False)
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info['id']
            title = info.get('title','Video')[:60]
            video_path = None
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(video_id) and f.endswith(('.mp4','.mkv','.webm')):
                    video_path = os.path.join(DOWNLOAD_DIR, f)
                    break
            if not video_path:
                for f in os.listdir(DOWNLOAD_DIR):
                    if video_id in f and f.endswith(('.mp4','.mkv','.webm')):
                        video_path = os.path.join(DOWNLOAD_DIR, f)
                        break
            if not video_path or not os.path.exists(video_path):
                raise Exception("Video topilmadi")
            await context.bot.send_video(
                chat_id=chat_id,
                video=open(video_path, 'rb'),
                caption=f"🎬 <b>{html.escape(title)}</b>",
                parse_mode='HTML',
                reply_markup=build_link_video_keyboard(video_id)
            )
            context.user_data[f'video_path_{video_id}'] = video_path
            context.user_data[f'video_title_{video_id}'] = title
            context.user_data[f'video_url_{video_id}'] = url
            try: await status_msg.delete()
            except: pass
            try:
                with open(TOP_FILE, "a", encoding="utf-8") as tf:
                    tf.write(f"{title}\n")
            except: pass
            return True
    except Exception as e:
        logging.error(f"Video download xato: {e}")
        try:
            await status_msg.edit_text(f"❌ <b>Video yuklanmadi:</b> {html.escape(str(e)[:100])} 😔", parse_mode='HTML')
            await asyncio.sleep(4)
            await status_msg.delete()
        except: pass
        return False

async def handle_voice_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_file = None
    file_path = None
    try:
        if update.message.voice:
            user_file = await update.message.voice.get_file()
            file_path = os.path.join(DOWNLOAD_DIR, f"voice_{user_file.file_id}.ogg")
        elif update.message.video:
            user_file = await update.message.video.get_file()
            file_path = os.path.join(DOWNLOAD_DIR, f"video_{user_file.file_id}.mp4")
        elif update.message.video_note:
            user_file = await update.message.video_note.get_file()
            file_path = os.path.join(DOWNLOAD_DIR, f"note_{user_file.file_id}.mp4")
        elif update.message.audio:
            user_file = await update.message.audio.get_file()
            file_path = os.path.join(DOWNLOAD_DIR, f"audio_{user_file.file_id}.mp3")
        elif update.message.document and update.message.document.mime_type and 'video' in update.message.document.mime_type:
            user_file = await update.message.document.get_file()
            file_path = os.path.join(DOWNLOAD_DIR, f"doc_{user_file.file_id}.mp4")
        else:
            return
        await user_file.download_to_drive(file_path)
        file_id_short = user_file.file_id[-20:]
        context.user_data[f'user_video_path_{file_id_short}'] = file_path
        text = (
            "🎬 <b>Videoyingizni tahrirlaymizmi?</b> ✨\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎧 Audiosini ajratib MP3 qilaymi?\n"
            "🔍 Ichidagi musiqani topib beraymi?\n"
            "👇 Tanlang!"
        )
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=build_user_video_keyboard(file_id_short))
    except Exception as e:
        logging.error(f"handle_voice_video xato: {e}")
        await update.message.reply_text("😔 <b>Xatolik yuz berdi, qayta yuboring!</b>", parse_mode='HTML')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        is_new = True
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                if str(user.id) in f.read():
                    is_new = False
        if is_new:
            with open(USERS_FILE, "a", encoding="utf-8") as f:
                f.write(f"{user.id}\n")
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_text = f"🆕 <b>YANGI USER START BOSDI! 🚀</b>\n👤 <b>Ism:</b> {user.first_name}\n🔗 <b>Username:</b> @{user.username or 'yoq'}\n🆔 <b>ID:</b> <code>{user.id}</code>\n⏰ <b>Vaqt:</b> {now}\n"
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
        log_to_admin = f"💬 <b>User javob berdi!</b>\n━━━━━━━━━━━━\n👤 {user.first_name} (@{user.username})\n🆔 <code>{user.id}</code>\n💌 Javobi:\n{html.escape(user_text)}"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✉ Javob berish", callback_data=f"admin_reply_{user.id}")]])
        await context.bot.send_message(chat_id=config.ADMIN_ID, text=log_to_admin, parse_mode='HTML', reply_markup=keyboard)
        thank_msg = await update.message.reply_text("✅ <b>Javobingiz uchun rahmat! Admin ko'radi.</b>", parse_mode='HTML')
        try:
            await asyncio.sleep(3)
            await context.bot.delete_message(chat_id=context.user_data['admin_chat_id'], message_id=context.user_data['admin_msg_id'])
            await context.bot.delete_message(chat_id=context.user_data['admin_chat_id'], message_id=context.user_data['prompt_msg_id'])
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=thank_msg.message_id)
        except: pass
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
        try:
            await update.message.delete()
        except: pass
        status = await context.bot.send_message(chat_id=update.effective_chat.id, text="⏳ <b>Boshlanmoqda...</b> ✨", parse_mode='HTML')
        if is_instagram_url(txt) or is_youtube_url(txt):
            ok = await download_and_send_video(txt, context, status, update.effective_chat.id)
            if not ok:
                await download_and_send(txt, context, status, update.effective_chat.id)
        else:
            ok, cap_v, title, video_url = await download_and_send(txt, context, status, update.effective_chat.id)
            if ok:
                context.user_data['pending_video_url'] = video_url
                context.user_data['pending_video_caption'] = cap_v
                context.user_data['pending_video_title'] = title
    else:
        status = await update.message.reply_text(f"🔍 <b>\"{html.escape(txt)}\" qidirilmoqda...</b> 🎵✨", parse_mode='HTML')
        results = search_youtube(txt)
        if not results:
            await status.edit_text("❌ <b>Topilmadi!</b> 😔")
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
                        [InlineKeyboardButton("🎧 MP3 ni Yuklash", url=f"https://t.me/{context.bot.username}?start={vid}")]
                    ])
                )
            )
        await update.inline_query.answer(articles, cache_time=0)
    except Exception as e:
        logging.error(f"Inline xato: {e}")

async def handle_user_video_buttons(query, context, file_id_short):
    chat_id = query.message.chat.id
    path = context.user_data.get(f'user_video_path_{file_id_short}')
    if not path or not os.path.exists(path):
        await context.bot.send_message(chat_id=chat_id, text="😔 <b>Fayl topilmadi, videoni qayta yuboring!</b>", parse_mode='HTML')
        try: await query.message.delete()
        except: pass
        return
    try:
        await query.message.delete()
    except: pass
    if query.data == f"uv_cut_{file_id_short}":
        status = await context.bot.send_message(chat_id=chat_id, text="✂ <b>Audiosi ajratilmoqda...</b> ⚡ Juda tez!", parse_mode='HTML')
        try:
            mp3_path = path.rsplit('.',1)[0] + "_cut.mp3"
            subprocess.run(['ffmpeg','-y','-i',path,'-vn','-ar','44100','-ac','2','-q:a','0',mp3_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 2000:
                await context.bot.send_audio(chat_id=chat_id, audio=open(mp3_path,'rb'), caption="🎧 <b>Ovozi ajratib olindi!</b> ✨", parse_mode='HTML', reply_markup=build_after_audio_keyboard())
                try: os.remove(mp3_path)
                except: pass
            try: await status.delete()
            except: pass
        except Exception as e:
            logging.error(e)
            try: await status.edit_text("❌ <b>Ajratib bo'lmadi!</b>", parse_mode='HTML')
            except: pass
    elif query.data == f"uv_shazam_{file_id_short}":
        status = await context.bot.send_message(chat_id=chat_id, text="🎧 <b>Eshitib ko'ryapman...</b> 👂✨\n🔍 <b>Musiqa qidirilmoqda...</b> 🎵", parse_mode='HTML')
        wav_path = None
        try:
            wav_path = path.rsplit('.',1)[0] + "_shazam.mp3"
            subprocess.run(['ffmpeg','-y','-i',path,'-ss','2','-t','12','-ar','44100','-ac','2',wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            shazam = Shazam()
            out = None
            if os.path.exists(wav_path):
                out = await shazam.recognize(wav_path)
            if out and out.get('track'):
                track = out['track']
                title = track.get('title','Noma\'lum')
                artist = track.get('subtitle','Noma\'lum')
                full_name = f"{artist} - {title}"
                await status.edit_text(f"🎉 <b>Topildi🥳</b>\n🎤 <b>{html.escape(artist)}</b>\n🎵 <b>{html.escape(title)}</b>\n\n📥 <b>Yuklanmoqda...</b> 🚀", parse_mode='HTML')
                results = search_youtube(full_name)
                if results:
                    url = f"https://www.youtube.com/watch?v={results[0]['id']}"
                    ok, cap_v, t, video_url = await download_and_send(url, context, status, chat_id)
                    if ok:
                        context.user_data['pending_video_url'] = video_url
                        context.user_data['pending_video_caption'] = cap_v
                        context.user_data['pending_video_title'] = t
                        return
            await status.edit_text("😔 <b>Musiqa tanilmadi!</b> 🎵", parse_mode='HTML')
        except Exception as e:
            logging.error(e)
            try: await status.edit_text("😔 <b>Musiqa tanilmadi!</b>", parse_mode='HTML')
            except: pass
        finally:
            if wav_path and os.path.exists(wav_path):
                try: os.remove(wav_path)
                except: pass

async def handle_link_video_buttons(query, context, video_id):
    chat_id = query.message.chat.id
    path = context.user_data.get(f'video_path_{video_id}')
    title = context.user_data.get(f'video_title_{video_id}', 'Video')
    url = context.user_data.get(f'video_url_{video_id}')
    if query.data == f"lv_no_{video_id}":
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except: pass
        return
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except: pass
    if query.data == f"lv_cut_{video_id}":
        if not path or not os.path.exists(path):
            if url:
                status = await context.bot.send_message(chat_id=chat_id, text="✂ <b>Audiosi qirqilmoqda...</b> ⚡", parse_mode='HTML')
                await download_and_send(url, context, status, chat_id)
                return
            return
        status = await context.bot.send_message(chat_id=chat_id, text="✂ <b>Audiosi qirqilmoqda...</b> ⚡", parse_mode='HTML')
        try:
            mp3_path = path.rsplit('.',1)[0] + "_lv_cut.mp3"
            subprocess.run(['ffmpeg','-y','-i',path,'-vn','-ar','44100','-ac','2','-q:a','0',mp3_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if os.path.exists(mp3_path):
                await context.bot.send_audio(chat_id=chat_id, audio=open(mp3_path,'rb'), caption=f"🎧 <b>{html.escape(title)}</b> ✨", parse_mode='HTML', reply_markup=build_after_audio_keyboard())
                context.user_data['pending_video_url'] = url
                context.user_data['pending_video_title'] = title
                try: os.remove(mp3_path)
                except: pass
            try: await status.delete()
            except: pass
        except Exception as e:
            logging.error(e)
    elif query.data == f"lv_search_{video_id}":
        if not path or not os.path.exists(path):
            await context.bot.send_message(chat_id=chat_id, text="😔 <b>Video fayli topilmadi!</b>", parse_mode='HTML')
            return
        status = await context.bot.send_message(chat_id=chat_id, text="🔍 <b>Videodagi musiqa qidirilmoqda...</b> 🎵✨", parse_mode='HTML')
        wav_path = None
        try:
            wav_path = path.rsplit('.',1)[0] + "_shazam.mp3"
            subprocess.run(['ffmpeg','-y','-i',path,'-ss','2','-t','12','-ar','44100','-ac','2',wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            shazam = Shazam()
            out = None
            if os.path.exists(wav_path):
                out = await shazam.recognize(wav_path)
            if out and out.get('track'):
                track = out['track']
                t_title = track.get('title','Noma\'lum')
                artist = track.get('subtitle','Noma\'lum')
                full_name = f"{artist} - {t_title}"
                await status.edit_text(f"🎉 <b>Topildi🥳</b>\n🎤 <b>{html.escape(artist)}</b>\n🎵 <b>{html.escape(t_title)}</b>\n\n📥 <b>Yuklanmoqda...</b> 🚀", parse_mode='HTML')
                results = search_youtube(full_name)
                if results:
                    url2 = f"https://www.youtube.com/watch?v={results[0]['id']}"
                    ok, cap_v, t, video_url = await download_and_send(url2, context, status, chat_id)
                    if ok:
                        context.user_data['pending_video_url'] = video_url
                        context.user_data['pending_video_title'] = t
            else:
                await status.edit_text("😔 <b>Musiqa topilmadi!</b> 🎵\nVideoda musiqa yo'q shekilli!", parse_mode='HTML')
        except Exception as e:
            logging.error(e)
            await status.edit_text("😔 <b>Musiqa topilmadi!</b>", parse_mode='HTML')
        finally:
            if wav_path and os.path.exists(wav_path):
                try: os.remove(wav_path)
                except: pass

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    if query.data.startswith("uv_"):
        if query.data.startswith("uv_cut_"):
            file_id_short = query.data.replace("uv_cut_", "")
        elif query.data.startswith("uv_shazam_"):
            file_id_short = query.data.replace("uv_shazam_", "")
        elif query.data.startswith("uv_cancel_"):
            try: await query.message.delete()
            except: pass
            return
        else:
            file_id_short = ""
        await handle_user_video_buttons(query, context, file_id_short)
        return

    if query.data.startswith("lv_"):
        try:
            if query.data.startswith("lv_search_"):
                video_id = query.data.replace("lv_search_", "")
            elif query.data.startswith("lv_cut_"):
                video_id = query.data.replace("lv_cut_", "")
            elif query.data.startswith("lv_no_"):
                video_id = query.data.replace("lv_no_", "")
            else:
                video_id = query.data.split("_")[-1]
            await handle_link_video_buttons(query, context, video_id)
        except Exception as e:
            logging.error(f"lv button xato: {e}")
        return

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

    if query.data.startswith("top_page_"):
        try:
            page = int(query.data.split("_")[-1])
            results = context.user_data.get('top_results', [])
            if not results: return
            text, _ = build_search_text("🔥 TOP 20 - Trend", results, page)
            total_pages = (len(results) + PER_PAGE - 1) // PER_PAGE
            start = page * PER_PAGE
            chunk = results[start:start+PER_PAGE]
            keyboard = []
            row = []
            for i, e in enumerate(chunk):
                row.append(InlineKeyboardButton(f"{start+i+1}", callback_data=f"dl_{e['id']}"))
                if len(row)==3:
                    keyboard.append(row); row=[]
            if row: keyboard.append(row)
            nav=[]
            if page>0: nav.append(InlineKeyboardButton("❤ Avvalgisi", callback_data=f"top_page_{page-1}"))
            if page<total_pages-1: nav.append(InlineKeyboardButton("🩷 Keyingisi", callback_data=f"top_page_{page+1}"))
            if nav: keyboard.append(nav)
            kb = InlineKeyboardMarkup(keyboard)
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
        context.user_data['pending_video_url'] = None
        context.user_data['pending_video_title'] = None
        context.user_data['pending_video_caption'] = None
    elif query.data == "lyrics_yes":
        title = context.user_data.get('pending_video_title') or 'Qo\'shiq'
        safe_title = html.escape(title)
        status_lyrics = await context.bot.send_message(chat_id=chat_id, text=f"🎤 <b>{safe_title}</b> uchun so'zlar qidirilmoqda... 📜✨", parse_mode='HTML')
        lyrics = get_lyrics(title)
        try: await status_lyrics.delete()
        except: pass
        if lyrics:
            pretty = f"🎤 <b>{html.escape(title)}</b>\n━━━━━━━━━━━━━━━━━━━━━━\n<pre>{html.escape(lyrics[:3500])}</pre>\n━━━━━━━━━━━━━━━━━━━━━━\n🤖 @{context.bot.username}"
            await context.bot.send_message(chat_id=chat_id, text=pretty, parse_mode='HTML')
        else:
            await context.bot.send_message(chat_id=chat_id, text=f"😔 <b>{html.escape(title)}</b> uchun so'zlar topilmadi... 🥲", parse_mode='HTML')
    elif query.data == "want_video_yes":
        url = context.user_data.get('pending_video_url')
        if url:
            status = await context.bot.send_message(chat_id=chat_id, text="📹 <b>Video yuklanmoqda...</b> 🎬", parse_mode='HTML')
            ydl_opts = get_ydl_opts(url, audio_only=False)
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    video_id = info['id']
                    video_path = None
                    for f in os.listdir(DOWNLOAD_DIR):
                        if f.startswith(video_id) and f.endswith(('.mp4','.mkv','.webm')):
                            video_path = os.path.join(DOWNLOAD_DIR, f)
                            break
                if video_path and os.path.exists(video_path):
                    await context.bot.send_video(chat_id=chat_id, video=open(video_path, 'rb'), caption=f"🎵 <b>{html.escape(context.user_data.get('pending_video_title',''))}</b>", parse_mode='HTML', reply_markup=build_link_video_keyboard(video_id))
                    context.user_data[f'video_path_{video_id}'] = video_path
                    context.user_data[f'video_title_{video_id}'] = context.user_data.get('pending_video_title','')
                    context.user_data[f'video_url_{video_id}'] = url
            except Exception as e:
                logging.error(e)
            try: await status.delete()
            except: pass
    elif query.data.startswith("effect_"):
        effect = query.data.split("_")[1]
        title = context.user_data.get('pending_video_title', 'Audio')
        url = context.user_data.get('pending_video_url')
        if not url:
            await context.bot.send_message(chat_id=chat_id, text="😔 <b>Asl musiqa topilmadi! Iltimos qayta yuklang!</b>", parse_mode='HTML')
            return
        status_eff = await context.bot.send_message(chat_id=chat_id, text=f"✨ <b>{effect} effekti qilinmoqda...</b> 🎧", parse_mode='HTML')
        tmp_path = None; eff_path = None
        try:
            ydl_opts = get_ydl_opts(url, audio_only=True)
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                vid = info['id']
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(vid):
                        tmp_path = os.path.join(DOWNLOAD_DIR, f)
                        break
            if tmp_path:
                eff_path = apply_audio_effect(tmp_path, effect)
                if eff_path:
                    cap = f"🎧 <b>{html.escape(title)}</b> - {effect} ✨"
                    await context.bot.send_audio(chat_id=chat_id, audio=open(eff_path,'rb'), title=f"{title} ({effect})", caption=cap, parse_mode='HTML', reply_markup=build_after_audio_keyboard())
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

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!= config.ADMIN_ID:
        await update.effective_message.reply_text("⛔ Siz admin emassiz!")
        return
    if update.message.reply_to_message:
        admin_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or "Xabar"
    else:
        if not context.args:
            await update.message.reply_text("📢 Foydalanish: <code>/broadcast Salom!</code> yoki xabarga reply qilib /broadcast", parse_mode='HTML')
            return
        admin_text = " ".join(context.args)
    if not os.path.exists(USERS_FILE):
        await update.message.reply_text("😔 Hali user yo'q!")
        return
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = [int(line.strip()) for line in f if line.strip().isdigit()]
    text, keyboard = build_admin_message(admin_text)
    status = await update.message.reply_text(f"🚀 {len(users)} ta userga yuborilmoqda...", parse_mode='HTML')
    success = 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=text, parse_mode='HTML', reply_markup=keyboard)
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await status.edit_text(f"✅ {success} ta userga professional xabar yuborildi!")

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

async def top_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from collections import Counter
    if not os.path.exists(TOP_FILE):
        await update.message.reply_text("😔 Hali TOP ro'yxat bo'sh! Birorta musiqa yuklang!")
        return
    try:
        with open(TOP_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except:
        lines = []
    if not lines:
        await update.message.reply_text("😔 Hali TOP ro'yxat bo'sh!")
        return
    counter = Counter(lines)
    top_20_titles = [title for title, count in counter.most_common(20)]
    status = await update.message.reply_text("🔥 <b>TOP 20 tayyorlanmoqda...</b> ⏳", parse_mode='HTML')
    results = []
    for t in top_20_titles:
        try:
            res = search_youtube(t)
            if res:
                results.append(res[0])
        except: pass
        if len(results) >= 20:
            break
    if not results:
        await status.edit_text("😔 TOP ni chiqarib bo'lmadi!")
        return
    context.user_data['top_results'] = results
    context.user_data['top_page'] = 0
    text, _ = build_search_text("🔥 TOP 20 - Trend", results, 0)
    def build_top_keyboard(results, page):
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
            nav_row.append(InlineKeyboardButton("❤ Avvalgisi", callback_data=f"top_page_{page-1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("🩷 Keyingisi", callback_data=f"top_page_{page+1}"))
        if nav_row:
            keyboard.append(nav_row)
        return InlineKeyboardMarkup(keyboard)
    kb = build_top_keyboard(results, 0)
    await status.edit_text(text, parse_mode='HTML', reply_markup=kb)

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.ADMIN_ID:
        await update.message.reply_text("⛔ Siz admin emassiz!")
        return
    total = 0
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            total = len([line for line in f if line.strip().isdigit()])
    size_kb = 0
    if os.path.exists(USERS_FILE):
        size_kb = os.path.getsize(USERS_FILE) / 1024
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
    print(f"🤖 {config.BOT_NAME} ishga tushdi... ✨")
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("send", send_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("stat", stats_cmd))
    app.add_handler(CommandHandler("users", stats_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.VIDEO | filters.VIDEO_NOTE | filters.AUDIO | filters.Document.VIDEO, handle_voice_video))
    app.run_polling()

if __name__ == '__main__':
    main()
