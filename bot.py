import os
import logging
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================
# تنظیمات اصلی
# =========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "outputs"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================================
# دستور /start
# =========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! 👋\n\n"
        "من ربات فشرده‌ساز ویدیو هستم 🎬\n\n"
        "کافیه یه ویدیو برام بفرستی، ازت می‌پرسم چقدر حجمش رو کم کنم، "
        "بعد نسخه سبک‌تر رو برات می‌فرستم!\n\n"
        "⚠️ حداکثر حجم: 50 مگابایت (محدودیت تلگرام)"
    )

# =========================================
# دریافت ویدیو
# =========================================
async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    # هم ویدیوی مستقیم، هم فایل ارسال‌شده به عنوان Document
    if message.video:
        file_obj = message.video
        file_size_mb = file_obj.file_size / (1024 * 1024)
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("video"):
        file_obj = message.document
        file_size_mb = file_obj.file_size / (1024 * 1024)
    else:
        await message.reply_text("لطفاً یه فایل ویدیویی بفرست 🎬")
        return

    if file_size_mb > 50:
        await message.reply_text(
            f"❌ حجم فایل {file_size_mb:.1f} مگابایته.\n"
            "متأسفانه تلگرام اجازه دانلود بیشتر از 50 مگابایت رو نمیده."
        )
        return

    # ذخیره اطلاعات فایل برای استفاده بعدی
    context.user_data["file_id"] = file_obj.file_id
    context.user_data["file_size_mb"] = file_size_mb

    # نمایش کیبورد انتخاب درصد فشرده‌سازی
    keyboard = [
        [
            InlineKeyboardButton("30٪ کاهش حجم", callback_data="30"),
            InlineKeyboardButton("50٪ کاهش حجم", callback_data="50"),
        ],
        [
            InlineKeyboardButton("70٪ کاهش حجم", callback_data="70"),
            InlineKeyboardButton("80٪ کاهش حجم", callback_data="80"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        f"✅ ویدیو دریافت شد! ({file_size_mb:.1f} MB)\n\n"
        "تا چند درصد می‌خوای حجمش کم بشه؟ 👇",
        reply_markup=reply_markup,
    )

# =========================================
# پردازش انتخاب درصد
# =========================================
async def handle_compression_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    percent = int(query.data)  # مثلاً 50
    file_id = context.user_data.get("file_id")
    file_size_mb = context.user_data.get("file_size_mb", 0)

    if not file_id:
        await query.edit_message_text("❌ ویدیو پیدا نشد. لطفاً دوباره ویدیو بفرست.")
        return

    await query.edit_message_text(
        f"⏳ در حال فشرده‌سازی با {percent}٪ کاهش حجم...\n"
        "لطفاً چند لحظه صبر کن 🎬"
    )

    try:
        # دانلود ویدیو از تلگرام
        file = await context.bot.get_file(file_id)
        input_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp4")
        output_path = os.path.join(OUTPUT_DIR, f"{file_id}_compressed.mp4")

        await file.download_to_drive(input_path)

        # محاسبه CRF برای رسیدن به درصد کاهش موردنظر
        # CRF: عدد بزرگتر = فشرده‌سازی بیشتر (کیفیت کمتر)
        # 30% کاهش → CRF 28
        # 50% کاهش → CRF 32
        # 70% کاهش → CRF 36
        # 80% کاهش → CRF 40
        crf_map = {30: 28, 50: 32, 70: 36, 80: 40}
        crf = crf_map.get(percent, 32)

        # فشرده‌سازی با FFmpeg
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vcodec", "libx264",
            "-crf", str(crf),
            "-preset", "fast",
            "-acodec", "aac",
            "-b:a", "128k",
            output_path
        ]

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            await query.edit_message_text(
                "❌ خطا در فشرده‌سازی ویدیو.\n"
                "لطفاً دوباره امتحان کن."
            )
            return

        # محاسبه حجم خروجی
        output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
        actual_reduction = (1 - output_size_mb / file_size_mb) * 100

        # ارسال ویدیوی فشرده‌شده
        with open(output_path, "rb") as video_file:
            await context.bot.send_video(
                chat_id=query.message.chat_id,
                video=video_file,
                caption=(
                    f"✅ فشرده‌سازی انجام شد!\n\n"
                    f"📦 حجم اولیه: {file_size_mb:.1f} MB\n"
                    f"📦 حجم جدید: {output_size_mb:.1f} MB\n"
                    f"📉 کاهش واقعی: {actual_reduction:.0f}٪"
                )
            )

        await query.edit_message_text("✅ ویدیو فشرده‌شده برات فرستاده شد! 🎉")

    except subprocess.TimeoutExpired:
        await query.edit_message_text("❌ فشرده‌سازی خیلی طول کشید. ویدیو رو دوباره بفرست.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await query.edit_message_text(f"❌ خطایی پیش اومد: {str(e)}")
    finally:
        # پاک کردن فایل‌های موقت
        for path in [input_path, output_path]:
            if os.path.exists(path):
                os.remove(path)

# =========================================
# اجرای ربات
# =========================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, receive_video))
    app.add_handler(CallbackQueryHandler(handle_compression_choice))

    print("✅ ربات شروع به کار کرد!")
    app.run_polling()

if __name__ == "__main__":
    main()
