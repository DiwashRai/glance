from app.types import Provider

# ---- Provider Registry ---------------------------------------------------------------------


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, type[Provider]] = {}

    def register(self, provider_cls: type[Provider]) -> None:
        kind = getattr(provider_cls, "kind", None)

        if not isinstance(kind, str) or not kind:
            raise ValueError(f"{provider_cls!r} must define a non-empty class attribute 'kind'")

        if kind in self._providers:
            raise ValueError(f"Provider '{kind}' is already registered")

        self._providers[kind] = provider_cls

    def create(self, kind: str) -> Provider:
        try:
            provider_cls = self._providers[kind]
        except KeyError as exc:
            available = ", ".join(sorted(self._providers))
            raise ValueError(
                f"Unknown provider '{kind}'. Available providers: {available}"
            ) from exc

        return provider_cls()

    def names(self) -> list[str]:
        return sorted(self._providers.keys())


provider_registry = ProviderRegistry()
