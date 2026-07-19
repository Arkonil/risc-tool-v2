import typing
from uuid import UUID

from risc_tool.data.models.enums import Signature
from risc_tool.data.models.sentinel_int import SentinelInt

ChangeID = tuple[Signature, UUID]
ChangeIDs = set[ChangeID]
CallbackID = UUID
Callback = typing.Callable[[ChangeIDs], bool]


class DataSourceID(SentinelInt):
    TEMPORARY: "DataSourceID"
    EMPTY: "DataSourceID"

    @classmethod
    def validate_sentinel(cls, v: int) -> "DataSourceID":
        if v == int(cls.TEMPORARY):
            return cls.TEMPORARY
        if v == int(cls.EMPTY):
            return cls.EMPTY

        return super().validate_sentinel(v)


DataSourceID.TEMPORARY = DataSourceID(-1, name="TEMPORARY")
DataSourceID.EMPTY = DataSourceID(-2, name="EMPTY")
