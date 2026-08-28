from typing import Literal

from .editing import modify_message
from ..backend.cache import TTLCache
from ..backend.config import Config
from ..backend.database import Database, Guild, MessageLink
from ..backend.models import Proxy
from ..backend.utils import convert_attachments, quote
from ..service import Webhook, Context, Attachment, Embed

webhook_cache = TTLCache[int, Webhook](2048, 3600)


async def get_webhook(context: Context) -> Webhook:
    if webhook := webhook_cache.get(context.message.channel_id): return webhook
    webhook = None

    if webhook_id := await Database.instance.get_channel_webhook(context.message.channel_id, context.platform):
        webhook = await context.get_bot.get_webhook(webhook_id)

    if webhook is None:
        webhook = await context.channel.create_webhook(Config.instance.webhook)
        await Database.instance.put_channel_webhook_link(context.message.channel_id, webhook.id, context.platform)

    webhook_cache.set(context.message.channel_id, webhook)
    return webhook


async def send_proxy_message(proxy: Proxy, message: str, context: Context, attachments: list[Attachment], mention: bool, do_reply: bool) -> Context:
    webhook: Webhook = await get_webhook(context)
    channel = await context.get_this_channel()

    mention_str: str | Literal[False] = False
    ref = await context.message.get_reference()

    if ref:
        lnk = await Database.instance.get_message_link(ref.id, ref.channel_id)
        if lnk and (parent_proxy := await Database.instance.get_proxy(lnk.proxy_id)):
            mention_str = f"{parent_proxy.name} (<@{lnk.platform_user}>)"
        else:
            mention_str = ref.author.mention

    message, embeds = await modify_message(
        proxy.owner,
        await Database.instance.get_guild_preferences(Guild(channel.guild_id, context.platform)),
        message
    )

    if ref and do_reply:
        return await webhook.reply(
            ref.context, message, proxy.effective_name, proxy.effective_avatar, mention, embeds,
            await convert_attachments(attachments), mention_str
        )

    return await webhook.send(
        message, proxy.effective_name, proxy.effective_avatar, mention, embeds, await convert_attachments(attachments)
    )


async def reproxy(context: Context, old_proxy: Proxy, new_proxy: Proxy):
    assert isinstance(old_proxy.id, int)
    assert isinstance(new_proxy.id, int)

    webhook: Webhook = await get_webhook(context)
    if (channel := await context.get_channel(context.message.channel_id)) is None:
        return

    guild = Guild(channel.guild_id, context.platform)
    server_preferences = await Database.instance.get_guild_preferences(guild)

    fixed_message = await webhook.get_message_data(context)
    contents = fixed_message.content
    attachments = fixed_message.attachments
    embeds = fixed_message.embeds
    parent_message = await fixed_message.get_reference()

    previous_link: MessageLink = await Database.instance.get_message_link(context.message.id, context.message.channel_id)
    await context.message.delete()
    await Database.instance.delete_link_message(context.message.id, context.channel.id)
    if parent_message:
        m = await webhook.reply(
            parent_message.context, contents, new_proxy.effective_name, new_proxy.effective_avatar, True, embeds,
            await convert_attachments(attachments), False
        )
    else:
        m = await webhook.send(
            contents, new_proxy.effective_name, new_proxy.effective_avatar, True, embeds, await convert_attachments(attachments)
        )

    await Database.instance.transfer_proxy_usage(old_proxy.id, new_proxy.id)
    await Database.instance.set_autoproxy_last_used_proxy(old_proxy.owner, guild, new_proxy.id)
    await Database.instance.link_message(m.id, context.channel.id, new_proxy.id, previous_link.platform_user, context.platform)
    logging_channel_id = server_preferences.logging_channel
    if logging_channel_id != 0 and (logging_channel := await context.get_channel(logging_channel_id)):
        embed = Embed(
            f"Message Proxy Change",
            f"**Previous Proxy**: {old_proxy.effective_name}\n**New Proxy**: {new_proxy.effective_name}\n**Owner**: <@{previous_link.platform_user}> (`{previous_link.platform_user}`)\n**Channel**: {context.channel.mention} (`{context.channel.id}`)\n**New Message Link**: [jump]({await m.message.mention()})",
            thumbnail_url=new_proxy.effective_avatar
        )
        await logging_channel.send("", embeds=[embed])


async def edit_proxy_message(old_message: Context, new_message_contents: str, message_link: MessageLink, owner: int):
    webhook: Webhook = await get_webhook(old_message)
    if (channel := await old_message.get_channel(old_message.message.channel_id)) is None:
        return

    guild = Guild(channel.guild_id, old_message.platform)

    server_preferences = await Database.instance.get_guild_preferences(guild)
    contents, embeds = await modify_message(owner, server_preferences, new_message_contents)

    await webhook.edit(
        old_message,
        contents,
        embeds
    )

    logging_channel_id = server_preferences.logging_channel
    if logging_channel_id != 0 and (logging_channel := await old_message.get_channel(logging_channel_id)) and (proxy := await Database.instance.get_proxy(message_link.proxy_id)):
        embed = Embed(
            f"Message Edit",
            f"**Proxy**: {proxy.effective_name}\n**Owner**: <@{message_link.platform_user}> (`{message_link.platform_user}`)\n**Channel**: <#{old_message.message.channel_id}> (`{old_message.message.channel_id}`)\n**Message Link**: [jump]({await old_message.message.mention()})\n**Old Message**:\n{quote(old_message.content)}\n**New Message**:\n{quote(new_message_contents)}",
            thumbnail_url=proxy.effective_avatar
        )
        await logging_channel.send("", embeds=[embed])