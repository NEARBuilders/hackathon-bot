"""The bot's own replies to /start and /help, and plain descriptions in Telegram's / menu. Hermes
answers /start with nothing (just the 👍 reaction), /help with its internal command list and labels
the menu in developer terms, so a new user's first taps looked like a dead end or a developer
screen. /start and /help are answered directly, before Hermes sees them: fixed text, no model call. In groups only /start@thisbot and /help@thisbot count, like every other command there;
a plain /start or /help is for other bots.
"""

GREETING = """Hi! I answer questions about NEAR Hackathon (1–14 Nov 2026): rules, deadlines, tracks, prizes, submitting, and building on NEAR.

Just ask, for example: "when is the submission deadline?"

Run by NEAR Builders, not the organizers. Official source: nearhackathon.com"""

HELP = """Ask me anything about NEAR Hackathon or building on NEAR.

In groups, mention @NearHackathonBot or reply to one of my messages.

/new – start a fresh conversation
/help – show this message"""

MENU = {
    "slash.new.description": "Start a fresh conversation",
    "slash.help.description": "What I can help with",
}


def _handlers(app, adapter):
    from telegram import LinkPreviewOptions
    from telegram.ext import CommandHandler

    def reply_with(text):
        async def handler(update, context):
            message = update.effective_message
            # CommandHandler already skips /help@otherbot, so an @ here means this bot.
            if message.chat.type != "private" and "@" not in message.text.split()[0]:
                return
            await message.reply_text(text, link_preview_options=LinkPreviewOptions(is_disabled=True))
        return handler

    app.add_handler(CommandHandler("start", reply_with(GREETING)))
    app.add_handler(CommandHandler("help", reply_with(HELP)))


def register(ctx):
    ctx.register_telegram_handler(_handlers)
    ctx.register_locale("en", MENU)
