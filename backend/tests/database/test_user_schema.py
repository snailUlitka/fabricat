"""Database schema specific tests."""

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from sqlalchemy import Table

from fabricat_backend.database.schemas import UserSchema
from fabricat_backend.shared import AvatarIcon


def test_user_schema_icon_uses_enum_values() -> None:
    table = cast("Table", UserSchema.__table__)
    icon_column = table.c.icon
    assert icon_column.type.enums == [icon.value for icon in AvatarIcon]
