from dataclasses import dataclass

from ..backend.models import Proxy
from ..backend.database import UserAutoproxyPreference, Database, AUTOPROXY_USE_SPOTLIGHT
from ..backend.template_utils import Template
from ..backend.utils import normalize_emojis


@dataclass(slots=True)
class MatchResult:
    value: str | None

    def matched(self) -> bool:
        return self.value is not None

    def match(self) -> str:
        if self.value is None:
            raise ValueError()
        return self.value


@dataclass(slots=True)
class ProxiedMessage:
    proxy: Proxy
    message: str


def text_matches_trigger(text: str, triggers: list[str]) -> MatchResult:
    for trigger in triggers:
        if trigger:
            trigger_norm = normalize_emojis(trigger)
            text_norm = normalize_emojis(text)
            res = Template.from_string(trigger_norm).match(text_norm)
            if res.match:
                return MatchResult(res.content)
    return MatchResult(None)


async def get_proxy_from_text(text: str, user_proxies: list[Proxy]) -> ProxiedMessage | None:
    for proxy in user_proxies:
        if proxy.triggers:
            if (res := text_matches_trigger(text, proxy.triggers)).matched():
                return ProxiedMessage(proxy, res.match())
    return None


async def get_first_spotlight_proxies(uid: int) -> Proxy | None:
    user_settings = await Database.instance.get_user_preferences(uid)
    spotlights = user_settings.spotlight
    if spotlights:
        return await Database.instance.get_proxy(spotlights[0])

    return None


async def get_proxied_messages(message: str, user_id: int, autoproxy_preferences: UserAutoproxyPreference | None) -> list[ProxiedMessage]:
    res: list[ProxiedMessage] = []
    autoproxy_proxy = None
    user_proxies = await Database.instance.get_user_proxies(user_id)

    if autoproxy_preferences and not autoproxy_preferences.expires_now():
        if (autoproxy_preferences.get_flags() & AUTOPROXY_USE_SPOTLIGHT) == AUTOPROXY_USE_SPOTLIGHT:
            autoproxy_proxy = await get_first_spotlight_proxies(user_id)
        else:
            prox_id = autoproxy_preferences.proxy if autoproxy_preferences.proxy is not None else autoproxy_preferences.last_used_proxy
            if prox_id is None:
                return []
            autoproxy_proxy = await Database.instance.get_proxy(prox_id)

    previous_proxied_message: ProxiedMessage | None = None
    for line in message.split("\n"):
        if proxied_message := await get_proxy_from_text(line, user_proxies):
            res.append(proxied_message)
            previous_proxied_message = proxied_message
        elif previous_proxied_message: # proxy is not found for this line and there's a previous proxied message, meaning it's a continued line.
            previous_proxied_message.message += "\n" + line
        else: # no proxy was found and no previous proxied message, meaning no proxy is used, or that it is an autoproxy.
            if autoproxy_proxy:
                if line.startswith("\\") and not line.startswith("\\\\"):
                    return []
                res.append(ProxiedMessage(autoproxy_proxy, line))
            else:
                return []
    return res

