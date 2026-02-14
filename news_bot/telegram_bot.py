from __future__ import annotations

import asyncio
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Conflict, InvalidToken, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from news_bot.cleaner import ContentCleaner
from news_bot.config import Settings
from news_bot.database import Database
from news_bot.models import NewsStatus, QueueType
from news_bot.queue_manager import QueueManager
from news_bot.state_manager import StateManager

logger = logging.getLogger(__name__)


class TelegramController:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        state_manager: StateManager,
        queue_manager: QueueManager,
        cleaner: ContentCleaner,
    ) -> None:
        self.settings = settings
        self.db = db
        self.state_manager = state_manager
        self.queue_manager = queue_manager
        self.cleaner = cleaner
        self.app: Application | None = None
        self.enabled = False
        self._polling_stopped_due_conflict = False
        token = (settings.telegram_token or "").strip()
        if token:
            try:
                self.app = Application.builder().token(token).build()
                self._register_handlers()
                self.enabled = True
            except InvalidToken:
                logger.error("Invalid Telegram bot token provided; Telegram control disabled")
        else:
            logger.warning("Telegram bot token is not set; Telegram control disabled")

    def _register_handlers(self) -> None:
        if not self.app:
            return
        self.app.add_handler(CommandHandler("start", self.on_start))
        self.app.add_handler(CommandHandler("on", self.on_on))
        self.app.add_handler(CommandHandler("off", self.on_off))
        self.app.add_handler(CommandHandler("reset", self.on_reset))
        self.app.add_handler(CommandHandler("status", self.on_status))
        self.app.add_handler(CommandHandler("adduser", self.on_add_user))
        self.app.add_handler(CommandHandler("user", self.on_select_user))
        self.app.add_handler(CommandHandler("profile", self.on_select_profile))
        self.app.add_handler(CommandHandler("addurl", self.on_add_url))
        self.app.add_handler(CommandHandler("blacklist", self.on_blacklist))
        self.app.add_handler(MessageHandler(filters.Regex(r"^\d{6}$"), self.on_otp))
        self.app.add_handler(CallbackQueryHandler(self.on_callback, pattern=r"^(publish|delete|profile|userselect):"))

    async def start(self) -> None:
        if not self.enabled or not self.app:
            return
        await self.app.initialize()
        await self.app.start()
        if self.app.updater:
            await self.app.updater.start_polling(error_callback=self._polling_error_handler)
        await self._send_startup_message()

    def _polling_error_handler(self, error: TelegramError) -> None:
        if isinstance(error, Conflict):
            if self._polling_stopped_due_conflict:
                return
            self._polling_stopped_due_conflict = True
            logger.error(
                "Telegram polling conflict detected: another process is already using this bot token. "
                "Stopping polling in this process."
            )
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.warning("No running event loop available to stop updater immediately")
                return
            loop.create_task(self._stop_polling_only())
            return
        logger.exception("Telegram polling error: %s", error)

    async def _stop_polling_only(self) -> None:
        if not self.app or not self.app.updater:
            return
        try:
            await self.app.updater.stop()
        except Exception:
            logger.exception("Failed to stop Telegram updater after conflict")

    async def _send_startup_message(self) -> None:
        if not self.app:
            return
        if not self.settings.allowed_chat_id:
            logger.info("Telegram is running. Set TELEGRAM_ALLOWED_CHAT_ID to receive startup/welcome message.")
            return
        try:
            await self.app.bot.send_message(
                chat_id=self.settings.allowed_chat_id,
                text="✅ News automation bot started. Please choose a profile to begin setup:",
                reply_markup=self._profile_keyboard(),
            )
        except TelegramError:
            logger.exception("Failed to send startup message to allowed chat")

    async def stop(self) -> None:
        if not self.enabled or not self.app:
            return
        if self.app.updater:
            await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()

    async def _authorized(self, update: Update) -> bool:
        if not self.settings.allowed_chat_id:
            return True
        chat = update.effective_chat
        return bool(chat and chat.id == self.settings.allowed_chat_id)

    def _profile_keyboard(self) -> InlineKeyboardMarkup:
        keyboard = [[InlineKeyboardButton("didbaniran", callback_data="profile:didbaniran")]]
        return InlineKeyboardMarkup(keyboard)

    async def _user_keyboard(self) -> InlineKeyboardMarkup | None:
        users = await self.db.fetchall("SELECT username FROM cms_users ORDER BY created_at DESC")
        if not users:
            return None
        keyboard = [[InlineKeyboardButton(row["username"], callback_data=f"userselect:{row['username']}")] for row in users]
        return InlineKeyboardMarkup(keyboard)

    async def on_start(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        state = await self.state_manager.get_state()
        text = (
            "✅ News bot is online.\n"
            f"Status: {state.get('bot_status')}\n"
            f"Profile: {state.get('selected_profile')}\n"
            f"User: {state.get('selected_user') or 'not selected'}\n"
            "Step 1: choose profile."
        )
        await update.effective_message.reply_text(text, reply_markup=self._profile_keyboard())

    async def on_on(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        await self.state_manager.set_bot_status("ON")
        await update.effective_message.reply_text("Bot is ON")

    async def on_off(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        await self.state_manager.set_bot_status("OFF")
        await self.queue_manager.clear()
        await update.effective_message.reply_text("Bot is OFF and queues cleared")

    async def on_reset(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        await self.queue_manager.stop()
        self.queue_manager.start()
        await update.effective_message.reply_text("Workers restarted")

    async def on_status(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        state = await self.state_manager.get_state()
        await update.effective_message.reply_text(str(state))

    async def on_add_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        args = context.args
        if len(args) != 2:
            await update.effective_message.reply_text("Usage: /adduser <username> <password>")
            return
        await self.db.execute(
            "INSERT OR REPLACE INTO cms_users(username, password, created_at) VALUES (?, ?, datetime('now'))",
            (args[0], args[1]),
        )
        await update.effective_message.reply_text(f"User added: {args[0]}. Now choose user.")
        keyboard = await self._user_keyboard()
        if keyboard:
            await update.effective_message.reply_text("Step 2: choose CMS user", reply_markup=keyboard)

    async def on_select_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if not context.args:
            keyboard = await self._user_keyboard()
            if keyboard:
                await update.effective_message.reply_text("Choose user", reply_markup=keyboard)
            else:
                await update.effective_message.reply_text("No users found. Add one with /adduser <username> <password>")
            return
        await self.state_manager.set_selected_user(context.args[0])
        await self.state_manager.set_bot_status("ON")
        await update.effective_message.reply_text(f"Selected user: {context.args[0]} | Bot is ON")

    async def on_select_profile(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        await update.effective_message.reply_text("Step 1: Select profile", reply_markup=self._profile_keyboard())

    async def on_add_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        if not context.args:
            await update.effective_message.reply_text("Usage: /addurl <url>")
            return
        source_url = context.args[0]
        row = await self.db.fetchone("SELECT id FROM news WHERE source_url = ?", (source_url,))
        if row:
            await self.db.add_queue(row["id"], QueueType.SCRAPE, priority=1)
            await update.effective_message.reply_text("Queued existing URL")
            return
        await update.effective_message.reply_text("URL not found in database yet")

    async def on_blacklist(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        phrase = " ".join(context.args).strip()
        if not phrase:
            await update.effective_message.reply_text("Usage: /blacklist <phrase>")
            return
        await self.cleaner.add_blacklist_phrase(phrase)
        await update.effective_message.reply_text("Blacklist phrase added")

    async def on_otp(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._authorized(update):
            return
        text = (update.effective_message.text or "").strip()
        if self.state_manager.submit_otp(text):
            await update.effective_message.reply_text("OTP received")

    async def on_callback(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        data = query.data or ""
        if data.startswith("profile:"):
            profile = data.split(":", 1)[1]
            await self.state_manager.set_profile(profile)
            keyboard = await self._user_keyboard()
            if keyboard:
                await query.edit_message_text(f"Profile set: {profile}. Step 2: choose CMS user")
                await query.message.reply_text("Choose user", reply_markup=keyboard)
            else:
                await query.edit_message_text(
                    f"Profile set: {profile}. No CMS user found. Add one with /adduser <username> <password>")
            return
        if data.startswith("userselect:"):
            username = data.split(":", 1)[1]
            await self.state_manager.set_selected_user(username)
            await self.state_manager.set_bot_status("ON")
            await query.edit_message_text(f"Selected user: {username}. Bot is ON. RSS monitoring and queues are active.")
            return
        action, news_id = data.split(":", 1)
        if action == "publish":
            await self.db.add_queue(news_id, QueueType.PUBLISH, priority=1)
            await query.edit_message_text("Added to publish queue")
        elif action == "delete":
            await self.db.execute("UPDATE news SET status = ? WHERE id = ?", (NewsStatus.DELETED.value, news_id))
            await query.edit_message_text("Deleted")

    async def send_uploaded_notification(self, news_id: str, title: str, edit_url: str) -> None:
        if not self.enabled or not self.app or not self.settings.allowed_chat_id:
            return
        keyboard = [[
            InlineKeyboardButton("Publish", callback_data=f"publish:{news_id}"),
            InlineKeyboardButton("Delete", callback_data=f"delete:{news_id}"),
        ]]
        await self.app.bot.send_message(
            chat_id=self.settings.allowed_chat_id,
            text=f"Uploaded: {title}\n{edit_url}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
