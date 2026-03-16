from functools import lru_cache
from typing import Optional

from app.core.config import get_settings
from app.infrastructure.external.openfang.client import OpenFangClient


@lru_cache()
def get_openfang_client() -> Optional[OpenFangClient]:
    settings = get_settings()
    if settings.agent_runtime != "openfang":
        return None
    if not settings.openfang_base_url:
        return None
    return OpenFangClient(
        base_url=settings.openfang_base_url,
        api_key=settings.openfang_api_key,
        default_template=settings.openfang_template,
    )
