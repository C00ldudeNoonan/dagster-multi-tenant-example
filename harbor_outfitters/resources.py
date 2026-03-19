from __future__ import annotations

import os

from shared.io_managers import make_duckdb_io_manager
from shared.resources import CatalogCoach


def get_resources() -> dict[str, object]:
    return {
        "llm": CatalogCoach(
            model_name=os.getenv("TENANT_ALPHA_MODEL", "qwen2.5:0.5b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300")),
            lock_path=os.getenv("OLLAMA_LOCK_PATH", "data/.ollama_generate.lock"),
            lock_timeout_seconds=float(os.getenv("OLLAMA_LOCK_TIMEOUT_SECONDS", "900")),
            runtime_dependency_package="catalog_coach_runtime",
        ),
        "io_manager": make_duckdb_io_manager("harbor_outfitters"),
    }
