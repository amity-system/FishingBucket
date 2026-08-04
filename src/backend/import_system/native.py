import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, AnyHttpUrl, NonNegativeInt

from . import Exporter
from .common import Importer
from ..models import ProxyTag, Proxy, ID


class NativeTag(BaseModel):
    name: str
    description: str
    creation_date: datetime
    tag: str


class NativeProxy(BaseModel):
    name: str
    description: str
    avatar_url: AnyHttpUrl | Literal[""]
    triggers: list[str]
    times_used: NonNegativeInt
    creation_date: datetime
    nickname: str
    forms: dict[str, AnyHttpUrl | Literal[""]]
    current_form: str
    pronouns: str
    tags: list[str]


class NativeRoot(BaseModel):
    proxies: list[NativeProxy]
    tags: dict[str, NativeTag]


class NativeImporter(Importer):
    def import_data(self, data: bytes, owner: int):
        root = NativeRoot(**json.loads(data.decode("utf-8")))

        parsed_tags: dict[str, ProxyTag] = {}
        for idx, tag in root.tags.items():
            t = ProxyTag(
                None,
                tag.name,
                tag.description,
                owner,
                tag.creation_date.timestamp(),
                tag.tag
            )
            self.tags.append(t)
            parsed_tags[idx] = t

        for proxy in root.proxies:
            tags = [parsed_tags[idx] for idx in proxy.tags]

            p = Proxy(
                None,
                proxy.name,
                proxy.description,
                str(proxy.avatar_url),
                proxy.triggers,
                owner,
                proxy.times_used,
                proxy.creation_date.timestamp(),
                proxy.nickname,
                {
                    k: str(v)
                    for k, v in proxy.forms.items()
                },
                proxy.current_form,
                proxy.pronouns,
                tags,
                True
            )
            self.proxies.append(p)


class NativeExporter(Exporter):
    def export_data(self) -> bytes:
        tags: dict[str, NativeTag] = {}
        proxies: list[NativeProxy] = []

        tag_idx_map: dict[ID, str] = {}

        for i, tag in enumerate(self.tags):
            assert tag.id is not None
            t = NativeTag(
                name=tag.name,
                description=tag.description,
                creation_date=datetime.fromtimestamp(tag.creation_date),
                tag=tag.tag
            )
            idx = f"${i}"
            tag_idx_map[tag.id] = idx
            tags[idx] = t

        for proxy in self.proxies:
            p = NativeProxy(
                name=proxy.name,
                description=proxy.description,
                avatar_url=proxy.avatar_url,
                triggers=proxy.triggers,
                times_used=proxy.times_used,
                creation_date=datetime.fromtimestamp(proxy.creation_date),
                nickname=proxy.nickname,
                forms=proxy.forms,
                current_form=proxy.current_form,
                pronouns=proxy.pronouns,
                tags=[
                    tag_idx_map[
                        tag.id # type: ignore
                    ] for tag in proxy.tags
                ]
            )
            proxies.append(p)

        root = NativeRoot(
            proxies=proxies,
            tags=tags
        )

        return root.model_dump_json().encode("utf-8")


    @property
    def filename(self) -> str:
        return "fishing_bucket.json"