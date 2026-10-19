"""What the collector and its providers share."""

from collections.abc import Mapping
from typing import Annotated, TypeAlias

import msgspec

NonEmpty = Annotated[str, msgspec.Meta(min_length=1)]
Table: TypeAlias = Mapping[str, object]  # a TOML table, before the provider it's for checks it
CountsRow: TypeAlias = tuple[str, str, int, int]  # label, icon, count, level
