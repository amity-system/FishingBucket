from typing import Literal

from .editing import is_replace, do_replace
from .executor import get_webhook, edit_proxy_message, send_proxy_message
from .matcher import get_proxied_messages
from ..backend.database import Guild, Database, MessageLink, GuildPreference
from ..backend.logging import start_log
from ..backend.utils import quote
from ..commands.specific import get_uid
from ..service import Context, Webhook, Channel, Embed

print, error = start_log("send_proxy", "-prox")

async def on_user_message(context: Context):
    channel = await context.get_this_channel()

    if channel.dm:
        return

    owner = await get_uid(context, on_unregistered=...)
    guild = Guild(channel.guild_id, context.platform)
    if (member := await context.get_member(context.author.id)) is None: return

    roles = await member.roles()

    if await Database.instance.get_allow_proxy(
            channel.id,
            guild,
            [role.id for role in roles][::-1],
            context.author.id
    ):
        autoproxy_prefs = await Database.instance.get_autoproxy_preference(owner, guild)

        replace = is_replace(context.content)
        if replace:
            message_id = await Database.instance.get_latest_proxy_message_from_user(context.channel.id, owner, context.platform)
            if (message := await context.channel.get_message(message_id)) is None or not message_id:
                return
            message_link: MessageLink = await Database.instance.get_message_link(message_id, context.channel.id)
            webhook: Webhook = await get_webhook(message.context)
            new_context = await webhook.get_message_data(message.context)
            if (proxy := await Database.instance.get_proxy(message_link.proxy_id)) is None:
                return

            await edit_proxy_message(
                message.context,
                do_replace(replace, new_context.content),
                message_link,
                proxy.owner
            )
            await context.message.delete()
            return

        print(f"Message [{hash(context.message)}] trying to match")
        proxied = await get_proxied_messages(context.content, owner, autoproxy_prefs)
        print(f"Message [{hash(context.message)}] match subroutine completed")
        if proxied:
            logging_channel: Channel | None | Literal[False] = None
            ctx = None

            for i, proxied_message in enumerate(proxied):
                proxy = proxied_message.proxy
                assert isinstance(proxy.id, int)

                if not (proxied_message.message or context.message.attachments):
                    return
                try:
                    ctx = await send_proxy_message(
                        proxied_message.proxy,
                        proxied_message.message,
                        context,
                        context.message.attachments,
                        True,
                        i == 0
                    )

                except Exception as e:
                    error(e)
                    await context.reply(f"Messages could not be proxied! `{e}`")
                    return

                if ctx:
                    await Database.instance.link_message(ctx.id, ctx.message.channel_id, proxy.id, context.author.id, context.platform)

                if logging_channel is None:
                    server_preferences: GuildPreference = await Database.instance.get_guild_preferences(guild)
                    logging_channel_id = server_preferences.logging_channel
                    if logging_channel_id != 0:
                        logging_channel = await context.get_channel(logging_channel_id)
                    else:
                        logging_channel = False

                if logging_channel:
                    if ctx:
                        message_mention = await ctx.message.mention()
                        ref = await context.message.get_reference()
                        reply_msg = f"**Replying To**: [message link]({await ref.mention()})\n" if ref and i == 0 else ""
                        embed = Embed(
                            f"Proxied Message",
                            f"**Proxy**: {proxy.effective_name}\n**Owner**: {context.author.mention} (`{context.author.id}`)\n**Channel**: {context.channel.mention} (`{context.channel.id}`)\n**Message Link**: [jump]({message_mention})\n{reply_msg}**Message**:\n{quote(proxied_message.message)}",
                            thumbnail_url=proxy.effective_avatar
                        )
                        await logging_channel.send("", [embed])

                await Database.instance.use_proxy(proxy.id)

            if proxied:
                assert isinstance(proxied[0].proxy.id, int)
                await Database.instance.set_autoproxy_last_used_proxy(owner, guild, proxied[0].proxy.id)

            await context.message.delete()
