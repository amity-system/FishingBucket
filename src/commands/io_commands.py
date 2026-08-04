import json

import pydantic
from aiohttp import ClientSession

from .generic import hook_command
from .specific import get_uid
from ..backend.database import Database
from ..backend.import_system import NativeImporter, TupperboxImporter, PluralKitImporter, UtterImporter, NativeExporter, \
    Importer, OldNativeImporter
from ..backend.logging import start_log
from ..backend.models import ProxyTag, Proxy
from ..service import Context, Embed, File

print, error = start_log("im/exporter")


def setup():
    @hook_command("import")
    async def _(context: Context, file: str | None, origin: str | None):
        if not context.message.attachments and not file:
            await context.reply("Error: no import file found.")
            return

        if file:
            filename = file.split("?")[0].split("/")[-1]
            async with ClientSession() as session:
                async with session.get(file) as response:
                    contents = await response.read()
        else:
            filename = context.message.attachments[0].filename
            contents = await context.message.attachments[0].read()

        origin = origin or (
            "fishing_bucket_old" if "proxies" in filename and filename.endswith(".json") else
            "fishing_bucket" if "fishing" in filename and "bucket" in filename and filename.endswith(".json") else
            "tupperbox" if "tupper" in filename and filename.endswith(".json") else
            "pluralkit" if "system" in filename and filename.endswith(".json") else
            "utter" if "utter" in filename and filename.endswith(".json") else
            None
        )

        if origin is None:
            await context.reply(f"Error: cannot guess import file origin with the filename {filename!r}.")
            return

        origin_names = {
            "fishing_bucket_old": "Fishing Bucket (pre v18)",
            "fishing_bucket": "Fishing Bucket",
            "tupperbox": "Tupperbox",
            "pluralkit": "PluralKit",
            "utter": "Utter"
        }

        confirmation = await context.reply(f"Importing from {origin_names[origin]}")
        try:
            await context.message.delete()
        except: pass

        owner = await get_uid(context, True)

        cls: Importer

        if origin == "fishing_bucket":
            cls = NativeImporter()
        elif origin == "fishing_bucket_old":
            cls = OldNativeImporter()
        elif origin == "tupperbox":
            cls = TupperboxImporter()
        elif origin == "pluralkit":
            cls = PluralKitImporter()
        elif origin == "utter":
            cls = UtterImporter()
        else:
            raise Exception("unreachable")

        try:
            cls.import_data(contents, owner)
        except (json.JSONDecodeError, pydantic.ValidationError) as e:
            error(e)
            await confirmation.reply(f"Error: cannot parse file")
            return

        user_proxies = await Database.instance.get_user_proxies(owner)
        user_tags = await Database.instance.get_user_tags(owner)

        updated_proxies = 0
        updated_tags = 0

        inserted_proxy_instances: list[Proxy] = []
        inserted_tag_instances: list[ProxyTag] = []

        for tag in cls.tags:
            found_tag = [t for t in user_tags if t.name == tag.name]
            if found_tag:
                db_tag = found_tag[0]
                assert db_tag.id is not None

                await Database.instance.update_tag_description(db_tag.id, tag.description)
                await Database.instance.update_tag_tag(db_tag.id, tag.tag)
                updated_tags += 1
            else:
                inserted_tag_instances.append(await Database.instance.put_tag(tag))

        for proxy in cls.proxies:
            found_proxy = [p for p in user_proxies if p.name == proxy.name]
            if found_proxy:
                db_proxy = found_proxy[0]
                assert db_proxy.id is not None

                await Database.instance.update_description(db_proxy.id, proxy.description)
                await Database.instance.update_nickname(db_proxy.id, proxy.nickname)
                await Database.instance.update_avatar(db_proxy.id, proxy.avatar_url)
                await Database.instance.update_trigger(db_proxy.id, proxy.triggers)
                updated_proxies += 1
            else:
                inserted_proxy_instances.append(await Database.instance.put_proxy(proxy))

        inserted_proxies = len(cls.proxies) - updated_proxies
        inserted_tags = len(cls.tags) - updated_tags

        await confirmation.message.edit(
            f"Proxies loaded! Updated {updated_proxies} proxies and {updated_tags} tags, and inserted {inserted_proxies} new proxies and {inserted_tags} new tags!")

        proxies_text = "\n".join(
            f"- **{p.name}** (`{p.id}`)" for p in inserted_proxy_instances[:min(len(inserted_proxy_instances), 20)]
        ) or "- No proxies were added!"

        if len(inserted_proxy_instances) > 20:
            proxies_text += f"\n...... and {len(inserted_proxy_instances) - 20} more"

        groups_text = "\n".join(
            f"- **{t.name}** (`{t.id}`)" for t in inserted_tag_instances[:min(len(inserted_tag_instances), 20)]
        ) or "- No tags were added!"

        if len(inserted_tag_instances) > 20:
            groups_text += f"\n...... and {len(inserted_tag_instances) - 20} more"

        await confirmation.reply("", embeds=[
            Embed(
                f"{context.author.display_name}'s New Imports",
                f"New proxies:\n{proxies_text}\n\nNew tags:\n{groups_text}"
            )
        ])


    @hook_command("export")
    async def _(context: Context):
        owner = await get_uid(context)
        tags = await Database.instance.get_user_tags(owner)
        proxies = await Database.instance.get_user_proxies(owner)
        exporter = NativeExporter(proxies, tags)
        file = File(
            exporter.filename,
            "",
            exporter.export_data()
        )
        if not (await context.get_channel(context.message.channel_id)).dm:
            dm = await context.author.get_dm()
            await dm.send("Proxies exported!", files=[file])
            await context.reply("I've sent your exported proxies into your DM!")
        else:
            await context.reply("Proxies exported!", files=[file])
