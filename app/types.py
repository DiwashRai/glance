from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import (
    ClassVar,
    Literal,
    NamedTuple,
    NotRequired,
    Protocol,
    TypeAlias,
    TypedDict,
    TypeGuard,
    cast,
)

# ---- Renderer Types ------------------------------------------------------------------------

MonitorMode: TypeAlias = Literal["all", "primary"]
MonitorSelection = MonitorMode | list[int]
RenderMethod: TypeAlias = Callable[..., None]

# ---- TOML Types ----------------------------------------------------------------------------

TomlValue: TypeAlias = str | int | float | bool | list["TomlValue"] | dict[str, "TomlValue"]
TomlTable: TypeAlias = Mapping[str, TomlValue]

# ---- Provider Types ------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProviderContext:
    provider_name: str
    provider_config: TomlTable
    requests: list[TomlTable]


class CountProvider(Protocol):
    kind: ClassVar[str]

    def count(self, ctx: ProviderContext) -> int: ...


class TimeBlocksProvider(Protocol):
    kind: ClassVar[str]

    def time_blocks(self, ctx: ProviderContext) -> list["TimeBlockRow"]: ...


# ---- Status Payload Types ------------------------------------------------------------------


class CountsRow(NamedTuple):
    label: str
    icon: str
    value: int
    severity: int


class TimeBlockRow(NamedTuple):
    label: str
    due: str
    duration: int
    color_hex: str


class StatusFile(TypedDict):
    f: list[CountsRow]
    tb: NotRequired[list[TimeBlockRow]]


def is_str_list(value: object) -> TypeGuard[list[str]]:
    if not isinstance(value, list):
        return False
    value = cast(list[object], value)
    return len(value) == 0 or all(isinstance(item, str) for item in value)
