async def send_to_slack(text, user_name="Telegram"):
    if slack_client:
        try:
            slack_client.chat_postMessage(channel=SLACK_CHANNEL, text=f"[Telegram:{user_name}] {text}")
        except Exception as e:
            logger.error(f"Slack error: {e}")

import os,sys,logging,asyncio,base64,json
from slack_sdk import WebClient
import httpx
from anthropic import Anthropic
from telegram import Update,InlineKeyboardButton,InlineKeyboardMarkup
from telegram.ext import Application,CommandHandler,MessageHandler,CallbackQueryHandler,filters,ContextTypes

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s",level=logging.INFO)
logger=logging.getLogger(__name__)

TELEGRAM_TOKEN=os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY=os.environ.get("ANTHROPIC_API_KEY")
ALLOWED_USER_IDS=os.environ.get("ALLOWED_USER_IDS","")
N8N_WEBHOOK_URL=os.environ.get("N8N_WEBHOOK_URL","")
GOOGLE_SHEET_ID=os.environ.get("GOOGLE_SHEET_ID","")
GOOGLE_API_KEY=os.environ.get("GOOGLE_API_KEY","")

ALLOWED=set(int(x) for x in ALLOWED_USER_IDS.split(",") if x.strip())
claude=Anthropic(api_key=ANTHROPIC_API_KEY)
conversations={}
SLACK_TOKEN=os.environ.get("SLACK_BOT_TOKEN","")
slack_client=WebClient(token=SLACK_TOKEN) if SLACK_TOKEN else None
SLACK_CHANNEL="C09LX94R78X"

SYSTEM="あなたは株式会社Martial Artsの専用AIアシスタントです。代表取締役・長谷川光のTelegramから動作しています。モットー：炎であれ、昨日を超えろ、爪痕を残せ。簡潔・的確・行動志向で回答してください。"

def is_allowed(uid):
    return not ALLOWED or uid in ALLOWED

def ask_claude(uid,content):
    if uid not in conversations:conversations[uid]=[]
    conversations[uid].append({"role":"user","content":content})
    history=conversations[uid][-20:]
    r=claude.messages.create(model="claude-sonnet-4-20250514",max_tokens=2048,system=SYSTEM,messages=history)
    reply=r.content[0].text
    conversations[uid].append({"role":"assistant","content":reply})
    return reply

async def download_file(bot,file_id):
    f=await bot.get_file(file_id)
    async with httpx.AsyncClient() as c:
        r=await c.get(f.file_path)
        return r.content

async def show_menu(update,context):
    kb=[
        [InlineKeyboardButton("🏠 不動産",callback_data="real_estate"),InlineKeyboardButton("🔥 保険",callback_data="insurance")],
        [InlineKeyboardButton("☀️ 太陽光",callback_data="solar"),InlineKeyboardButton("💍 婚活",callback_data="marriage")],
        [InlineKeyboardButton("💧 浄水器",callback_data="water"),InlineKeyboardButton("🚗 レンタカー",callback_data="rental")],
        [InlineKeyboardButton("💬 AIチャット",callback_data="chat")]
    ]
    markup=InlineKeyboardMarkup(kb)
    text="🔥 *Martial Arts AI Bot*\n\n機能を選択、または直接メッセージでAIチャット"
    if update.callback_query:
        await update.callback_query.edit_message_text(text,reply_markup=markup,parse_mode="Markdown")
    else:
        await update.message.reply_text(text,reply_markup=markup,parse_mode="Markdown")

async def cmd_start(update,context):
    if not is_allowed(update.effective_user.id):await update.message.reply_text("⛔ アクセス権限なし");return
    await show_menu(update,context)

async def cmd_menu(update,context):
    if not is_allowed(update.effective_user.id):return
    await show_menu(update,context)

async def cmd_reset(update,context):
    uid=update.effective_user.id
    conversations.pop(uid,None);context.user_data.pop("mode",None)
    await update.message.reply_text("✅ リセット完了")

async def callback_handler(update,context):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id;data=q.data
    if data=="reset":
        conversations.pop(uid,None);context.user_data.pop("mode",None)
        await q.edit_message_text("✅ リセット完了\n/menu で戻る");return
    if data=="status":
        turns=len(conversations.get(uid,[]))//2
        await q.edit_message_text(f"📊 会話ターン:{turns}\nn8n:{'✅' if N8N_WEBHOOK_URL else '❌'}\nシート:{'✅' if GOOGLE_SHEET_ID else '❌'}\n\n/menu で戻る");return
    if data in modes:
        mode,msg=modes[data];context.user_data["mode"]=mode
        await q.edit_message_text(f"{msg}\n\n/menu で戻る")

async def handle_text(update,context):
    uid=update.effective_user.id
    if not is_allowed(uid):await update.message.reply_text("⛔ アクセス権限なし");return
    text=update.message.text.strip()
    user_name=update.message.from_user.first_name or "Unknown"
    await send_to_slack(text, user_name)
    user_name=update.message.from_user.first_name or "Unknown"
    await send_to_slack(text, user_name);mode=context.user_data.get("mode","chat")
    if mode=="sheet":
        if not GOOGLE_SHEET_ID:await update.message.reply_text("❌ GOOGLE_SHEET_ID未設定");return
        await update.message.reply_text("📊 シート連携はGOOGLE_SHEET_IDとGOOGLE_API_KEY設定後に使用可");return
    if mode=="n8n":
        if not N8N_WEBHOOK_URL:await update.message.reply_text("❌ N8N_WEBHOOK_URL未設定");return
        try:
            async with httpx.AsyncClient() as c:r=await c.post(N8N_WEBHOOK_URL,json={"user_id":uid,"message":text},timeout=10)
            await update.message.reply_text(f"✅ n8n送信完了\n{r.text[:200]}")
        except Exception as e:await update.message.reply_text(f"❌ {e}")
        return
    await update.message.reply_text("⏳ 考え中...")
    try:
        reply=await asyncio.to_thread(ask_claude,uid,text)
        await update.message.reply_text(reply)
    except Exception as e:await update.message.reply_text(f"❌ {e}")

async def handle_document(update,context):
    uid=update.effective_user.id
    if not is_allowed(uid):return
    await update.message.reply_text("📄 解析中...")
    try:
        doc=update.message.document;data=await download_file(update.get_bot(),doc.file_id);fname=doc.file_name or "file"
        if fname.endswith(".pdf"):
            b64=base64.standard_b64encode(data).decode()
            content=[{"type":"document","source":{"type":"base64","media_type":"application/pdf","data":b64}},{"type":"text","text":"このPDFを要約し重要ポイントを箇条書きで"}]
        else:
            text=data.decode("utf-8",errors="replace")
            content=f"ファイル({fname})を解析:\n\n{text[:8000]}"
        reply=await asyncio.to_thread(ask_claude,uid,content)
        await update.message.reply_text(reply)
    except Exception as e:await update.message.reply_text(f"❌ {e}")

async def handle_photo(update,context):
    uid=update.effective_user.id
    if not is_allowed(uid):return
    await update.message.reply_text("🖼 解析中...")
    try:
        photo=update.message.photo[-1];data=await download_file(update.get_bot(),photo.file_id)
        b64=base64.standard_b64encode(data).decode();caption=update.message.caption or "この画像を詳しく説明してください"
        content=[{"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}},{"type":"text","text":caption}]
        reply=await asyncio.to_thread(ask_claude,uid,content)
        await update.message.reply_text(reply)
    except Exception as e:await update.message.reply_text(f"❌ {e}")

async def handle_voice(update,context):
    uid=update.effective_user.id
    if not is_allowed(uid):return
    await update.message.reply_text(f"🎤 音声受信({update.message.voice.duration}秒)\nWhisper API連携で文字起こし可能です。\nN8N_WEBHOOK_URLを設定するとn8n経由で処理できます。")

def main():
    logger.info("🚀 Martial Arts AI Bot フル機能版起動")
    app=Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",cmd_start))
    app.add_handler(CommandHandler("menu",cmd_menu))
    app.add_handler(CommandHandler("reset",cmd_reset))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL,handle_document))
    app.add_handler(MessageHandler(filters.PHOTO,handle_photo))
    app.add_handler(MessageHandler(filters.VOICE,handle_voice))
    app.add_handler(MessageHandler(filters.TEXT&~filters.COMMAND,handle_text))
    logger.info("✅ ポーリング開始")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":
    main()
# 末尾に追記不要、既にtry/catchあり
