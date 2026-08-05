import time
from typing import Literal

from .generic import hook_command
from .specific import get_uid
from .utils import paged_proxy_tag_list, get_tags_text, paged_proxy_list
from ..backend.database import Database
from ..backend.models import ProxyTag, Proxy
from ..backend.template_utils import Template
from ..backend.utils import quote, normalize_emojis
from ..interaction import Interactions, Interaction
from ..service import Context, Embed, ReactionActionEvent


def setup():
    @hook_command("tag register")
    async def _(context: Context, name: str, description: str) -> None:
        t = await Database.instance.put_tag(
            ProxyTag(
                None,
                name,
                description,
                await get_uid(context, True),
                time.time(),
                ""
            )
        )
        description_text = ("\nDescription:\n" + quote(description)) if description else ""
        await context.reply("", [Embed(
            "Tag Registered!",
            f"The tag **{name}** (`{t.id}`) has been registered.{description_text}",
        )])

    @hook_command("tag list")
    async def _(context: Context, page: int, detailed: bool) -> None:
        channel = await context.get_this_channel()
        uid = await get_uid(context)

        await paged_proxy_tag_list(
            context,
            await Database.instance.get_user_tags(uid),
            f"Proxy Tags of {context.author.display_name}",
            page,
            channel.dm or detailed
        )

    @hook_command("tag info")
    async def _(context: Context, tag: ProxyTag, detailed: bool) -> None:
        channel = await context.get_this_channel()
        await context.reply("", [Embed(
            tag.name,
            get_tags_text(
                [tag],
                await Database.instance.get_user_preferences(await get_uid(context)),
                channel.dm or detailed
            )[0]
        )])

    @hook_command("tag members")
    async def _(context: Context, tag: ProxyTag, page: int, detailed: bool) -> None:
        channel = await context.get_this_channel()
        uid = await get_uid(context)
        proxies = await Database.instance.get_user_proxies(uid)
        filtered = [proxy for proxy in proxies if any(t.id == tag.id for t in proxy.tags)]

        await paged_proxy_list(
            context,
            filtered,
            f"Members of {context.author.display_name} in **{tag.name}**",
            page,
            channel.dm or detailed
        )

    @hook_command("tag set name")
    async def _(context: Context, tag: ProxyTag, name: str) -> None:
        assert tag.id is not None

        old_name = tag.name
        await Database.instance.update_tag_name(tag.id, name)
        await context.reply("", [Embed(
            f"Tag Updated!",
            f"The name for the previous *{old_name}* has been changed to **{name}**!"
        )])

    @hook_command("tag set description")
    async def _(context: Context, tag: ProxyTag, description: str) -> None:
        assert tag.id is not None

        await Database.instance.update_tag_description(tag.id, description)
        mod = "changed" if description else "cleared"

        await context.reply("", [Embed(
            f"Tag Updated!",
            f"The description for **{tag.name}** has been {mod}!"
        )])

    @hook_command("tag set marker")
    async def _(context: Context, tag: ProxyTag, marker: Template | None) -> None:
        assert tag.id is not None

        owner = await get_uid(context)

        if marker:
            assert marker.string is not None

            t = normalize_emojis(marker.string)
            await Database.instance.update_tag_tag(tag.id, t)
            tag.tag = t

            example_proxy = Proxy(
                None,
                "Example Proxy",
                "This is an example proxy.",
                Proxy.random_avatar(),
                ["{}"],
                owner,
                0,
                time.time(),
                "Proxy",
                {},
                "",
                "pronoun",
                [tag],
                True
            )
            description = f"The marker for **{tag.name}** has been changed! Proxies with this tag, when sent, will display as *{example_proxy.effective_name}*"
        else:
            await Database.instance.update_tag_tag(tag.id, ""),
            description = f"The marker for **{tag.name}** has been cleared!"

        await context.reply("", [Embed(
            "Tag Updated!",
            description
        )])

    @hook_command("tag delete")
    async def _(context: Context, tag: ProxyTag) -> None:
        m = await context.reply(f"> [!WARNING]\n> Are you sure you want to remove tag **{tag.name}**? React to the :white_check_mark: to confirm. This message will expire in 30 seconds.")
        await m.message.add_reaction("✅")

        async def cb(event: ReactionActionEvent) -> bool:
            assert tag.id is not None

            if event.emoji == "✅":
                await Database.instance.delete_tag(tag.id)
                await m.reply(f"Successfully removed tag **{tag.name}**!")
                return True
            return False

        Interactions.instance.add_interaction(m, Interaction(context.author.id, cb))

        if await Interactions.instance.wait_claim_after(30, m.id, m.platform):
            await m.message.edit("Tag delete confirmation expired.")
            await m.message.remove_reaction("✅")
