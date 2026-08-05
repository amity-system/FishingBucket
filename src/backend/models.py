import random
import time
from dataclasses import dataclass
import json
from enum import Enum, auto
from sqlite3 import Row

class ID(int):
    def __str__(self):
        return hex(self)


@dataclass
class ProxyTag:
    id: ID | None
    name: str
    description: str
    owner: int
    creation_date: float
    tag: str

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, ProxyTag):
            return self.id == other.id
        return False


    @classmethod
    def from_database(cls, row: Row) -> ProxyTag:
        return cls(
            ID(row["id"]),
            row["name"] or "",
            row["description"] or "",
            row["owner"],
            row["creation_date"] or time.time(),
            row["tag"] or ""
        )

    def make_template_object(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "creation_date": self.creation_date,
            "marker": self.tag
        }


@dataclass
class Proxy:
    id: ID | None
    name: str
    description: str
    avatar_url: str
    triggers: list[str]
    owner: int
    times_used: int
    creation_date: float
    nickname: str
    forms: dict[str, str]
    current_form: str
    pronouns: str
    tags: list[ProxyTag]
    tags_set: bool

    @staticmethod
    def random_avatar() -> str:
        return f"https://raw.githubusercontent.com/fluxerapp/fluxer/refs/tags/2026.703.173023/fluxer_static/avatars/{random.randint(0, 5)}.png"

    @classmethod
    def from_database(cls, row: Row) -> Proxy:
        return cls(
            ID(row["id"]),
            row["name"],
            row["description"],
            row["avatar_url"],
            row["triggers"].split("\n"),
            row["owner"],
            row["times_used"] or 0,
            row["creation_date"] or time.time(),
            row["nickname"] or "",
            json.loads(row["proxy_forms"] or "{}"),
            row["current_form"] or "",
            row["pronouns"] or "",
            [],
            False
        )


    def set_tags(self, tags: list[ProxyTag]):
        self.tags = tags
        self.tags_set = True


    @property
    def effective_name(self) -> str:
        from .template_utils import Template # i've sinned
        n = self.nickname or self.name
        tagged = [t for t in self.tags if t.tag]
        effective_tag = tagged[0] if tagged else None
        if effective_tag:
            n = Template.from_string(
                effective_tag.tag # type: ignore
            ).compute({
                "name": n,
                "proxy": {
                    "id": self.id,
                    "name": self.name,
                    "description": self.description,
                    "avatar_url": self.avatar_url,
                    "triggers": self.triggers,
                    "times_used": self.times_used,
                    "creation_date": self.creation_date,
                    "tags": [t.make_template_object() for t in self.tags],
                    "nickname": self.nickname,
                    "forms": self.forms,
                    "form": self.current_form,
                    "pronouns": self.pronouns or ""
                },
                "tag": effective_tag.make_template_object()
            }, n)
        return n

    @property
    def effective_avatar(self) -> str:
        return self.forms.get(self.current_form or "", self.avatar_url)


class Platform(Enum):
    Fluxer = auto()
    Discord = auto()

    def get(self) -> int:
        if self == Platform.Fluxer:
            return 0
        else:
            return 1

    @classmethod
    def from_(cls, id_: int) -> Platform:
        return [Platform.Fluxer, Platform.Discord][id_]