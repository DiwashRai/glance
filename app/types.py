"""What the collector and its providers share."""

from collections.abc import Mapping
from typing import Annotated

import msgspec

NonEmpty = Annotated[str, msgspec.Meta(min_length=1)]
type Table = Mapping[str, object]  # a TOML table, before the provider it's for checks it
type CountsRow = tuple[str, str, int, int]  # label, icon, count, level
