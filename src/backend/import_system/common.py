from abc import ABC, abstractmethod

from ..models import Proxy, ProxyTag


class Importer(ABC):
    def __init__(self):
        self.proxies: list[Proxy] = []
        self.tags: list[ProxyTag] = []

    @abstractmethod
    def import_data(self, data: bytes, owner: int): pass

    @staticmethod
    def sanitize_potential_template_fragment(fragment: str) -> str:
        return fragment.replace("{", "\\{").replace("}", "\\}")

class Exporter(ABC):
    def __init__(self, proxies: list[Proxy], tags: list[ProxyTag]):
        self.proxies = proxies
        self.tags = tags

    @abstractmethod
    def export_data(self) -> bytes: pass

    @property
    @abstractmethod
    def filename(self) -> str: pass
