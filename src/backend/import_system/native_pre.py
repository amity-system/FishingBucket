import json
from typing import Literal

from pydantic import BaseModel, AnyHttpUrl, PositiveFloat, NonNegativeInt

from .common import Importer
from ..models import ProxyTag, Proxy


class NativeGroup(BaseModel):
    name: str
    description: str
    time: PositiveFloat
    tag: str
    parent: str | None


class NativeProxy(BaseModel):
    name: str
    description: str
    avatar_url: AnyHttpUrl | Literal[""]
    triggers: list[str]
    times_used: NonNegativeInt
    time: PositiveFloat
    group: str | None
    nickname: str
    forms: dict[str, AnyHttpUrl | Literal[""]]
    current_form: str | None
    pronouns: str | None = None


class NativeRoot(BaseModel):
    proxies: list[NativeProxy]
    groups: dict[str, NativeGroup]


class OldNativeImporter(Importer):
    def import_data(self, data: bytes, owner: int):
        root = NativeRoot(**json.loads(data.decode("utf-8")))

        parsed_groups: dict[str, ProxyTag] = {}
        tag_requisites: dict[str, str | None] = {}
        groups_queue: dict[str, NativeGroup] = {}
        for idx, group in root.groups.items():
            g = ProxyTag(
                None,
                group.name,
                group.description,
                owner,
                group.time,
                group.tag
            )
            self.tags.append(g)
            parsed_groups[idx] = g
            groups_queue[idx] = group
            if group.parent:
                tag_requisites[idx] = group.parent

        for proxy in root.proxies:
            tags = [proxy.group]
            while tags[-1] in tag_requisites and tag_requisites[tags[-1]] is not None:
                tags.append(tag_requisites[tags[-1]])

            full_tags = [parsed_groups[tag] for tag in tags if tag is not None]

            self.proxies.append(Proxy(
                None,
                proxy.name,
                proxy.description,
                str(proxy.avatar_url),
                proxy.triggers,
                owner,
                proxy.times_used,
                proxy.time,
                proxy.nickname or "",
                {
                    k: str(v)
                    for k, v in proxy.forms.items()
                },
                proxy.current_form or "",
                proxy.pronouns or "",
                full_tags,
                True
            ))
