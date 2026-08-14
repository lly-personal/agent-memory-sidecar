from __future__ import annotations

from typing import Any


class CoreError(RuntimeError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        self.code = str(code)
        self.message = str(message)
        self.details = dict(details)
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
