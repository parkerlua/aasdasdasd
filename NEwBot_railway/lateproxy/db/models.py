from __future__ import annotations

from dataclasses import dataclass, field

STATUSES = ("pending", "active", "sold", "rejected", "delisted")


@dataclass
class Listing:
    id: int
    user_id: int
    category: str
    title: str
    data: dict = field(default_factory=dict)
    status: str = "pending"
    channel_msg_id: int | None = None
    approved_by: int | None = None
    created: str = ""

    @property
    def seller(self) -> dict:
        """{'id', 'username', 'name'} of who submitted it (stored inside the listing data)."""
        return self.data.get("_seller") or {"id": self.user_id, "username": None, "name": f"User {self.user_id}"}


@dataclass
class User:
    id: int
    username: str
    name: str
    banned: bool = False
