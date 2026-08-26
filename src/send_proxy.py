import textwrap
from datetime import datetime
from typing import Literal

import expr_dice_roller as dice
import re

import json5
from pydantic import BaseModel, AnyHttpUrl, field_validator, ValidationError

from .backend.cache import TTLCache
from .backend.config import Config
from .backend.database import Database, GuildPreference, UserAutoproxyPreference, Guild, MessageLink, \
    AUTOPROXY_USE_SPOTLIGHT
from .backend.logging import start_log
from .backend.models import Proxy
from .backend.template_utils import Template
from .backend.dice_environments import global_functions
from .backend.utils import convert_attachments, normalize_emojis, roll_dice
from .commands.specific import get_uid
from .service import Context, Webhook, Attachment, Embed, Channel
from .service.common import RawEmbed, Message

print, error = start_log("send_proxy", "-prox")


def message_matches_trigger(message: str, triggers: list[str]) -> tuple[bool, str]:
    for trigger in triggers:
        if trigger:
            nm = normalize_emojis(trigger)
            nmm = normalize_emojis(message)
            res = Template.from_string(nm).match(nmm)
            if res.match:
                return True, res.content
    return False, ""

async def get_proxy_from_message(message: str, user_proxies: list[Proxy]) -> tuple[Proxy, str] | None:
    for proxy in user_proxies:
        if proxy.triggers:
            if (res := message_matches_trigger(message, proxy.triggers))[0]:
                return proxy, res[1]
    return None


async def get_first_spotlight_proxies(uid: int) -> Proxy | None:
    user_settings = await Database.instance.get_user_preferences(uid)
    spotlights = user_settings.spotlight
    if spotlights:
        return await Database.instance.get_proxy(spotlights[0])

    return None


def is_replace(content: str) -> tuple[re.Pattern, str, bool] | None:
    if not content.startswith("\\s/"):
        return None
    content = content[len("\\s/"):]
    replacer = ""
    sub = ""
    global_ = False
    if content.endswith("/g"):
        global_ = True
        content = content[:-len("/g")]
    parsing = 0
    escape = False
    for i, char in enumerate(content):
        if not escape and char == "/" and parsing == 0:
            parsing = 1
            continue
        if char == "\\" and i < len(content) - 1 and content[i + 1] == "/":
            escape = True
            continue
        if parsing == 0:
            replacer += char
        elif parsing == 1:
            sub += char
    try:
        return re.compile(replacer, re.MULTILINE), sub, global_
    except re.PatternError:
        return None


def do_replace(replace: tuple[re.Pattern, str, bool], old_content: str) -> str:
    return replace[0].sub(replace[1], old_content, int(not replace[2]))


async def get_proxied_messages(message: str, user_id: int, autoproxy_preferences: UserAutoproxyPreference | None) -> list[tuple[Proxy, str]]:
    res: list[tuple[Proxy, str]] = []
    autoproxy_proxy = None
    user_proxies = await Database.instance.get_user_proxies(user_id)
    if autoproxy_preferences and not autoproxy_preferences.expires_now():
        if (autoproxy_preferences.get_flags() & AUTOPROXY_USE_SPOTLIGHT) == AUTOPROXY_USE_SPOTLIGHT:
            autoproxy_proxy = await get_first_spotlight_proxies(user_id)
        else:
            prox_id = autoproxy_preferences.proxy if autoproxy_preferences.proxy is not None else autoproxy_preferences.last_used_proxy
            autoproxy_proxy = await Database.instance.get_proxy(prox_id)
    for line in message.split("\n"):
        if proxy_m := await get_proxy_from_message(line, user_proxies):
            res.append(proxy_m)
        elif res: # proxy is not found for this line and there's a previous proxied message, meaning it's a continued line.
            res[-1] = (res[-1][0], res[-1][1] + "\n" + line)
        else: # no proxy was found and no previous proxied message, meaning no proxy is used, or that it is an autoproxy.
            if autoproxy_proxy:
                if res:
                    res[-1] = (res[-1][0], res[-1][1] + "\n" + line)
                else:
                    if line.startswith("\\") and not line.startswith("\\\\"):
                        return []
                    res.append((autoproxy_proxy, line))

            else:
                return []
    return res


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

    mention_str = None
    ref = await context.message.get_reference()

    if ref:
        lnk = await Database.instance.get_message_link(ref.id, ref.channel_id)
        if lnk:
            parent_proxy = await Database.instance.get_proxy(lnk.proxy_id)
            mention_str = f"{parent_proxy.name} (<@{lnk.platform_user}>)"
        else:
            mention_str = ref.author.mention

    message, embeds = await modify_message(proxy.owner, await Database.instance.get_guild_preferences(Guild(channel.guild_id, context.platform)), message, [])

    if ref and do_reply:
        return await webhook.reply(
            ref.context, message, proxy.effective_name, proxy.effective_avatar, mention, embeds,
            await convert_attachments(attachments), mention_str
        )

    return await webhook.send(
        message, proxy.effective_name, proxy.effective_avatar, mention, embeds, await convert_attachments(attachments)
    )


block_content_regex = re.compile(r"{{((?:.|\n)+?)}}(?!})")

class EmbedAuthor(BaseModel):
    name: str
    url: str | None = None
    icon_url: str | None = None

class EmbedImage(BaseModel):
    url: str
    description: str | None = None

class EmbedFooter(BaseModel):
    text: str
    icon_url: str | None = None

class EmbedField(BaseModel):
    name: str
    value: str
    inline: bool | None = None

class SingularEmbed(BaseModel):
    description: str
    url: str | None = None
    title: str | None = None
    color: int | None = None
    timestamp: datetime | None = None
    author: EmbedAuthor | str | None = None
    image: EmbedImage | str | None = None
    thumbnail: EmbedImage | str | None = None
    footer: EmbedFooter | str | None = None
    fields: list[EmbedField] | None = None

    @field_validator("author", mode="before")
    @classmethod
    def norm_author(cls, v: EmbedAuthor | str | None) -> EmbedAuthor | None:
        if isinstance(v, str):
            return EmbedAuthor(name=v)
        return v

    @field_validator("image", "thumbnail", mode="before")
    @classmethod
    def norm_image(cls, v: EmbedImage | str | None) -> EmbedImage | None:
        if isinstance(v, str):
            return EmbedImage(url=v)
        return v

    @field_validator("footer", mode="before")
    @classmethod
    def norm_footer(cls, v: EmbedFooter | str | None) -> EmbedFooter | None:
        if isinstance(v, str):
            return EmbedFooter(text=v)
        return v


def normalize_embed(embed: SingularEmbed) -> RawEmbed:
    return RawEmbed(embed.model_dump(exclude_defaults=True, mode="python"))

async def modify_message(user: int, guild_preferences: GuildPreference, message: str, embeds: list[Embed]) -> tuple[str, list[Embed]]:
    embed_list: list[Embed] = []
    evaluator = dice.Evaluator()
    fns = (await Database.instance.get_user_preferences(user)).dice_functions
    if fns:
        env = dice.Environment.deserialize(evaluator, fns)
    else:
        env = dice.Environment()
    guild_fns = guild_preferences.dice_functions
    if guild_fns:
        guild_env = dice.Environment.deserialize(evaluator, guild_fns)
    else:
        guild_env = dice.Environment()

    global_environment = global_functions()
    global_environment.mutable = env
    global_environment.immutable = guild_env

    def construct(match: re.Match) -> str:
        inner = match.group(1).strip()
        if inner.startswith("```") and inner.endswith("```"):
            inner = inner[3:-3]
        inner = textwrap.dedent(inner)

        do_embed = True
        j: dict | None = None
        parse_embed_error: ValidationError | None = None

        try:
            print("{" + inner + "}")
            j = json5.loads("{" + inner + "}")
        except ValueError:
            do_embed = False

        if do_embed:
            assert isinstance(j, dict)
            try:
                if "embeds" in j:
                    effective_embeds_list = [normalize_embed(SingularEmbed(**e)) for e in j["embeds"]]
                elif "embed" in j:
                    effective_embeds_list = [normalize_embed(SingularEmbed(**j["embed"]))]
                else:
                    raise ValidationError("embed blocks must either have an `embed` field or an `embeds` field.")

                embed_list.extend(effective_embeds_list)
                return ""
            except ValueError as e:
                parse_embed_error = e

        def get_global_environment(): return global_environment
        def set_global_environment(ge):
            nonlocal global_environment
            global_environment = ge

        if not do_embed:
            ret, embed = roll_dice(inner, get_global_environment, set_global_environment)
            embed_list.append(embed)
            return f"`{ret}`"
        else:
            embed_list.append(Embed(
                "Error parsing embed block",
                "```\n" + str(parse_embed_error) + "\n```"
            ))
            return ""

    result = block_content_regex.sub(construct, message), embed_list
    serialized = env.serialize()
    if serialized != fns:
        await Database.instance.set_user_preferences(user, dice_functions=serialized)
    return result


valid_dice_roll_description_regex = re.compile(r"`.+` = (\d+(?:\.\d*)?)")

def try_reverse_engineer(message: Message) -> str:
    i = 0
    replaces: list[tuple[slice, str]] = []
    for embed in message.raw_embeds:
        if embed.data.get("footer", {}).get("text") == "dice roll":
            description = embed.data["description"]
            if description.startswith("Error:"):
                start_index = message.content.find("`error`", i)
                i = start_index + len("`error`")
            elif match := valid_dice_roll_description_regex.match(description):
                result = match.group(1)
                start_index = message.content.find(f"`{result}`", i)
                i = start_index + len(f"`{result}`")
            else:
                start_index = message.content.find("`no value`", i)
                i = start_index + len("`no value`")

            replaces.append((slice(start_index, i), "{{" + embed.data["title"] + "}}"))
        else:
            replaces.append((slice(i, i), "{{embed: " + json5.dumps(normalize_embed(SingularEmbed(**embed.data)).data, indent=4) + "}}"))

    out = message.content
    for slicing, replace in replaces[::-1]:
        out = out[:slicing.start] + replace + out[slicing.stop:]

    return out


async def reproxy(context: Context, old_proxy: Proxy, new_proxy: Proxy):
    webhook: Webhook = await get_webhook(context)
    fixed_message = await webhook.get_message_data(context)
    contents = fixed_message.content
    attachments = fixed_message.attachments
    embeds = fixed_message.embeds
    parent_message = await fixed_message.get_reference()
    previous_link: MessageLink = await Database.instance.get_message_link(context.message.id, context.message.channel_id)
    guild = Guild((await context.get_channel(context.message.channel_id)).guild_id, context.platform)
    server_preferences = await Database.instance.get_guild_preferences(guild)
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
    if logging_channel_id != 0:
        logging_channel = await context.get_channel(logging_channel_id)
        embed = Embed(
            f"Message Proxy Change",
            f"**Previous Proxy**: {old_proxy.effective_name}\n**New Proxy**: {new_proxy.effective_name}\n**Owner**: <@{previous_link.platform_user}> (`{previous_link.platform_user}`)\n**Channel**: {context.channel.mention} (`{context.channel.id}`)\n**New Message Link**: [jump]({await m.message.mention()})",
            thumbnail_url=new_proxy.effective_avatar
        )
        await logging_channel.send("", embeds=[embed])


async def edit_proxy_message(old_message: Context, new_message_contents: str, message_link: MessageLink, owner: int):
    webhook: Webhook = await get_webhook(old_message)
    guild = Guild((await old_message.get_channel(old_message.message.channel_id)).guild_id, old_message.platform)

    server_preferences = await Database.instance.get_guild_preferences(guild)
    contents, embeds = await modify_message(owner, server_preferences, new_message_contents, [])

    await webhook.edit(
        old_message,
        contents,
        embeds
    )

    logging_channel_id = server_preferences.logging_channel
    if logging_channel_id != 0:
        logging_channel = await old_message.get_channel(logging_channel_id)
        proxy = await Database.instance.get_proxy(message_link.proxy_id)

        embed = Embed(
            f"Message Edit",
            f"**Proxy**: {proxy.effective_name}\n**Owner**: <@{message_link.platform_user}> (`{message_link.platform_user}`)\n**Channel**: <#{old_message.message.channel_id}> (`{old_message.message.channel_id}`)\n**Message Link**: [jump]({await old_message.message.mention()})\n**Old Message**:\n{'\n'.join('> ' + line for line in old_message.content.split('\n'))}\n**New Message**:\n{'\n'.join('> ' + line for line in new_message_contents.split('\n'))}",
            thumbnail_url=proxy.effective_avatar
        )
        await logging_channel.send("", embeds=[embed])


async def on_user_message(context: Context):
    channel = await context.get_this_channel()

    if channel.dm:
        return

    owner = await get_uid(context, on_unregistered=...)
    guild = Guild(channel.guild_id, context.platform)

    roles = await (await context.get_member(context.author.id)).roles()

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
            await edit_proxy_message(
                message.context,
                do_replace(replace, new_context.content),
                message_link,
                (await Database.instance.get_proxy(message_link.proxy_id)).owner
            )
            await context.message.delete()
            return

        print(f"Message [{hash(context.message)}] trying to match")
        proxied = await get_proxied_messages(context.content, owner, autoproxy_prefs)
        print(f"Message [{hash(context.message)}] match subroutine completed")
        if proxied:
            logging_channel: Channel | None | Literal[False] = None
            proxy = None
            ctx = None

            for i, (proxy, m) in enumerate(proxied):
                if not (m or context.message.attachments):
                    return

                try:
                    try:
                        ctx = await send_proxy_message(proxy, m, context, context.message.attachments, True, i == 0)
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
                            message_link = await ctx.message.mention()
                            ref = await context.message.get_reference()
                            reply_msg = f"**Replying To**: [message link]({await ref.mention()})\n" if ref and i == 0 else ""
                            embed = Embed(
                                f"Proxied Message",
                                f"**Proxy**: {proxy.effective_name}\n**Owner**: {context.author.mention} (`{context.author.id}`)\n**Channel**: {context.channel.mention} (`{context.channel.id}`)\n**Message Link**: [jump]({message_link})\n{reply_msg}**Message**:\n{'\n'.join('> ' + line for line in m.split('\n'))}",
                                thumbnail_url=proxy.effective_avatar
                            )
                            await logging_channel.send("", [embed])

                except Exception as e:
                    error(e)
                    if not ctx:
                        await context.reply(f"Messages could not be proxied! `{e}`")
                        return

                await Database.instance.use_proxy(proxy.id)

            if proxy:
                await Database.instance.set_autoproxy_last_used_proxy(owner, guild, proxy.id)

            await context.message.delete()
