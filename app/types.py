from collections.abc import Callable
from typing import Literal, TypeAlias, TypedDict

MonitorMode: TypeAlias = Literal["all", "primary"]
MonitorSelection = MonitorMode | list[int]
StatusFileRow: TypeAlias = tuple[str, str, int, int]
StatusRow: TypeAlias = tuple[str, str, str]
RenderMethod: TypeAlias = Callable[..., None]
ProviderFunction: TypeAlias = Callable[..., int]


class StatusFile(TypedDict):
    f: list[StatusFileRow]
