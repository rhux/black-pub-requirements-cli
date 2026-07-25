from __future__ import annotations

import uuid
from typing import Protocol


class IdFactory(Protocol):
    def new_id(self) -> str: ...


class Uuid4Factory:
    def new_id(self) -> str:
        return str(uuid.uuid4())
