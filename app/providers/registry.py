from typing import Any

from app.types import CountProvider, TimeBlocksProvider

# ---- Provider Registry ---------------------------------------------------------------------


def validate_provider(provider_cls: object, provider_dict: dict[str, Any]) -> str:
    kind = getattr(provider_cls, "kind", None)
    if not isinstance(kind, str) or not kind:
        raise ValueError(f"{provider_cls!r} must define a non-empty class attribute 'kind'")
    if kind in provider_dict:
        raise ValueError(f"Provider '{kind}' is already registered")
    return kind


class ProviderRegistry:
    def __init__(self) -> None:
        self._count_providers: dict[str, type[CountProvider]] = {}
        self._timeblocks_providers: dict[str, type[TimeBlocksProvider]] = {}

    def register_count_provider(self, provider_cls: type[CountProvider]) -> None:
        kind = validate_provider(provider_cls, self._count_providers)
        self._count_providers[kind] = provider_cls

    def register_timeblocks_provider(self, provider_cls: type[TimeBlocksProvider]) -> None:
        kind = validate_provider(provider_cls, self._timeblocks_providers)
        self._timeblocks_providers[kind] = provider_cls

    def create_count_provider(self, kind: str) -> CountProvider:
        try:
            provider_cls = self._count_providers[kind]
        except KeyError as exc:
            available = ", ".join(sorted(self._count_providers))
            raise ValueError(
                f"Unknown provider '{kind}'. Available providers: {available}"
            ) from exc

        return provider_cls()

    def create_timeblocks_provider(self, kind: str) -> TimeBlocksProvider:
        try:
            provider_cls = self._timeblocks_providers[kind]
        except KeyError as exc:
            available = ", ".join(sorted(self._count_providers))
            raise ValueError(
                f"Unknown provider '{kind}'. Available providers: {available}"
            ) from exc

        return provider_cls()


provider_registry = ProviderRegistry()
