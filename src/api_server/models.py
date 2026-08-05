from typing import Literal
from pydantic import BaseModel, Field

from ..backend import models as source_models

class EphemeralID(BaseModel):
    index: int

    def __hash__(self) -> int:
        return hash(f"new {self.index}")


class ProxyTag(BaseModel):
    id: int | EphemeralID
    name: str
    description: str
    creation_date: float
    tag: str

    @classmethod
    def from_source(cls, source: source_models.ProxyTag) -> ProxyTag:
        return cls(id=source.id, name=source.name, description=source.description,
                   creation_date=source.creation_date, tag=source.tag)

    def to_source(self, id_slot: int | None, owner: int) -> source_models.ProxyTag:
        return source_models.ProxyTag(
            source_models.ID(id_slot) if id_slot else None,
            self.name, self.description, owner, self.creation_date, self.tag
        )

class Proxy(BaseModel):
    id: int | EphemeralID
    name: str
    description: str
    avatar_url: str
    triggers: list[str]
    times_used: int
    creation_date: float
    tags: list[int | EphemeralID]
    nickname: str
    forms: dict[str, str]
    current_form: str
    effective_name: str
    pronouns: str

    @classmethod
    def from_source(cls, source: source_models.Proxy) -> Proxy:
        return cls(id=source.id, name=source.name, description=source.description, avatar_url=source.avatar_url,
                   triggers=source.triggers, times_used=source.times_used, creation_date=source.creation_date,
                   tags=[tag.id for tag in source.tags], nickname=source.nickname, forms=source.forms,
                   current_form=source.current_form, effective_name=source.effective_name, pronouns=source.pronouns)

    def to_source(self, id_slot: int | None, tags: list[source_models.ProxyTag], owner: int) -> source_models.Proxy:
        return source_models.Proxy(
            source_models.ID(id_slot) if id_slot else None,
            self.name, self.description, self.avatar_url, self.triggers, owner, self.times_used, self.creation_date,
            self.nickname, self.forms, self.current_form, self.pronouns, tags, True
        )


class NewProxyEdit(BaseModel):
    edit_type: Literal["NEW_PROXY"]
    proxy: Proxy

class NewProxyTagEdit(BaseModel):
    edit_type: Literal["NEW_PROXY_TAG"]
    tag: ProxyTag

class DeleteProxyEdit(BaseModel):
    edit_type: Literal["DELETE_PROXY"]
    proxy_id: int

class DeleteProxyTagEdit(BaseModel):
    edit_type: Literal["DELETE_PROXY_TAG"]
    tag_id: int

class EditProxyName(BaseModel):
    field: Literal["name"]
    value: str

class EditProxyDescription(BaseModel):
    field: Literal["description"]
    value: str

class EditProxyAvatarURL(BaseModel):
    field: Literal["avatar_url"]
    value: str

class EditProxyTriggers(BaseModel):
    field: Literal["triggers"]
    value: list[str]

class EditProxyTags(BaseModel):
    field: Literal["tags"]
    value: list[int | EphemeralID]

class EditProxyNickname(BaseModel):
    field: Literal["nickname"]
    value: str

class EditProxyForms(BaseModel):
    field: Literal["forms"]
    value: dict[str, str]

class EditProxyCurrentForm(BaseModel):
    field: Literal["current_form"]
    value: str

class EditProxyPronouns(BaseModel):
    field: Literal["pronouns"]
    value: str

class EditProxyField(BaseModel):
    edit_type: Literal["EDIT_PROXY_FIELD"]
    id: int | EphemeralID
    kv: (
        EditProxyName |
        EditProxyDescription |
        EditProxyAvatarURL |
        EditProxyTriggers |
        EditProxyTags |
        EditProxyNickname |
        EditProxyForms |
        EditProxyCurrentForm |
        EditProxyPronouns
    ) = Field(discriminator="field")

class EditProxyTagName(BaseModel):
    field: Literal["name"]
    value: str

class EditProxyTagDescription(BaseModel):
    field: Literal["description"]
    value: str

class EditProxyTagTag(BaseModel):
    field: Literal["tag"]
    value: str

class EditProxyTagField(BaseModel):
    edit_type: Literal["EDIT_PROXY_TAG_FIELD"]
    id: int | EphemeralID
    kv: (
        EditProxyTagName |
        EditProxyTagDescription |
        EditProxyTagTag
    ) = Field(discriminator="field")

class Edit(BaseModel):
    edit: (
            NewProxyEdit |
            NewProxyTagEdit |
            EditProxyField |
            EditProxyTagField |
            DeleteProxyEdit |
            DeleteProxyTagEdit
    ) = Field(discriminator="edit_type")

class BatchEdit(BaseModel):
    edits: list[Edit]

class ItemUpdateResponse[T](BaseModel):
    method: Literal["UPDATE"]
    id: int
    data: T

class ItemNewResponse[T](BaseModel):
    method: Literal["NEW"]
    id: int
    matching_ephemeral_id: int
    data: T

class ItemDeleteResponse[T](BaseModel):
    method: Literal["DELETE"]
    id: int

class ModifiedItem[T](BaseModel):
    type: Literal["PROXY"] | Literal["PROXY_TAG"]
    item: ItemUpdateResponse[T] | ItemNewResponse[T] | ItemDeleteResponse[T] = Field(discriminator="method")

class ModifiedItemResponse(BaseModel):
    items: list[ModifiedItem[Proxy | ProxyTag]]

class LoginInformation(BaseModel):
    session_id: str
    user: dict
    expires: float
    platform: Literal["discord"] | Literal["fluxer"]

class RefreshLogin(BaseModel):
    expires: float