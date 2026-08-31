from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Messages:
    en: dict[str, str]
    zh_cn: dict[str, str]

    def get(self, key: str) -> str:
        try:
            return self.zh_cn.get(key, self.en[key])
        except KeyError as error:
            raise KeyError(f"unknown message key: {key}") from error

    @classmethod
    def load_default(cls) -> Messages:
        path = Path(__file__).parent / "data" / "messages.toml"
        with path.open("rb") as message_file:
            document = tomllib.load(message_file)
        return cls(en=document["en"], zh_cn=document["zh_CN"])


MESSAGES = Messages.load_default()
