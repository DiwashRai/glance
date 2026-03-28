from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol, TypeAlias, TypedDict

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


class Provider(Protocol):
    kind: ClassVar[str]

    def count(self, ctx: ProviderContext) -> int: ...


# ---- Status Payload Types ------------------------------------------------------------------

CountsRow: TypeAlias = tuple[str, str, int, int]


class StatusFile(TypedDict):
    f: list[CountsRow]
