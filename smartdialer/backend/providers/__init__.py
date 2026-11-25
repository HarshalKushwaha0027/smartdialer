from .provider_a import ProviderA
from .provider_b import ProviderB

PROVIDERS = {
    "provider_a": ProviderA(),
    "provider_b": ProviderB(),
}


def get_provider(name: str):
    try:
        return PROVIDERS[name]
    except KeyError:
        raise ValueError(f"Unknown provider: {name}")
