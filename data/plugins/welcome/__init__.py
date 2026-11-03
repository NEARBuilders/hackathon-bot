"""The bot's own replies to /start and /help, and its / menu on Telegram and Discord. Hermes
answers /start with nothing (just the 👍 reaction), /help with its internal command list, labels
the Telegram menu in developer terms and publishes ~50 Discord slash commands, so a new user's first
taps looked like a dead end or a developer screen. /start and /help are answered directly, before
Hermes sees them: fixed text, no model call. In Telegram groups only /start@thisbot and /help@thisbot
count, like every other command there; a plain /start or /help is for other bots.

On Discord, Hermes' own slash commands are off (slash_commands: false in config.yaml) and so is its
command sync (DISCORD_COMMAND_SYNC_POLICY=off in deploy.sh): it would race this plugin and publish an
empty menu. This plugin publishes exactly /new and /help.

It also rewords Hermes' restart notices, which reach anyone mid-answer or writing during a deploy: they
named Hermes and promised to resume or queue, which a restart doesn't guarantee. And its notice for a
conversation it suspended, which named the model and offered a /resume users can't run.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

GREETING = """Hi! I answer questions about NEAR Hackathon (1–14 Nov 2026): rules, deadlines, tracks, prizes, submitting, and building on NEAR.

Just ask, for example: "when is the submission deadline?"

Run by NEAR Builders. Rules and submissions: nearhackathon.com"""

HELP = """Ask me anything about NEAR Hackathon or building on NEAR.

In {where}, mention {me} or reply to one of my messages.

/new – start a fresh conversation
/help – show this message"""

RESTARTING = "⏳ The bot is restarting for an update. If your answer doesn't arrive, please ask again in a minute."

NOTICES = {
    "gateway.shutdown.notice_shutdown": RESTARTING,
    "gateway.shutdown.notice_restart": RESTARTING,
    "gateway.busy.drain_queued": RESTARTING,
    "gateway.busy.drain_rejected": RESTARTING,
    "gateway.busy.drain_rejected_new_work": RESTARTING,
    # Hermes suspends a conversation stuck across several restarts and says so on its next message,
    # with a /resume tip and the model, provider and context size. (deploy.sh --reset doesn't
    # suspend: ops/fresh_start.py resets like /new, silently.)
    "gateway.session.auto_reset_notice": "New conversation started.",
    "gateway.session.info_model": "",
    "gateway.session.info_provider": "",
    "gateway.session.info_context": "",
}

MENU = {
    "slash.new.description": "Start a fresh conversation",
    "slash.help.description": "What I can help with",
}

_tasks = set()


def _telegram_handlers(app, adapter):
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
    app.add_handler(CommandHandler("help", reply_with(HELP.format(where="groups", me="@NearHackathonBot"))))


def _discord_handlers(bot, adapter):
    from discord import app_commands

    # Server installs only, whatever the Developer Portal says: a user-installed bot runs its
    # commands in any server, past the server lock (data/plugins/discord-server).
    server_only = app_commands.allowed_installs(guilds=True, users=False)

    # Hermes' own /new: its access checks, then the same reset as on Telegram.
    new = adapter._slash_proxy("new", (), "/new", None)
    bot.tree.command(name="new", description=MENU["slash.new.description"])(server_only(new))

    help_text = HELP.format(where="servers", me=bot.user.mention)

    @bot.tree.command(name="help", description=MENU["slash.help.description"])
    @server_only
    async def help_(interaction):
        await interaction.response.send_message(help_text, ephemeral=True, suppress_embeds=True)

    async def sync():
        try:
            await bot.tree.sync()
        except Exception:
            logger.exception("could not publish the Discord / menu")

    task = asyncio.get_running_loop().create_task(sync())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def register(ctx):
    ctx.register_telegram_handler(_telegram_handlers)
    ctx.register_platform_handler("discord", _discord_handlers)
    ctx.register_locale("en", {**MENU, **NOTICES})
