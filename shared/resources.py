from __future__ import annotations

import errno
import fcntl
import json
from importlib import metadata as importlib_metadata
import os
from pathlib import Path
import time
from typing import Any, Protocol
from urllib import error, request

import dagster as dg


class SupportsGenerate(Protocol):
    def generate(self, prompt: str) -> str:
        """Generate a text response for the provided prompt."""

    def runtime_metadata(self) -> dict[str, object]:
        """Return metadata describing the active model runtime."""


class OllamaLLMResource(dg.ConfigurableResource):
    model_name: str
    system_prompt: str
    base_url: str = "http://localhost:11434"
    timeout_seconds: float = 300.0
    lock_path: str = "data/.ollama_generate.lock"
    lock_timeout_seconds: float = 900.0
    runtime_dependency_package: str | None = None

    def generate(self, prompt: str) -> str:
        body = self._generate_with_lock(prompt)

        result = body.get("response")
        if not isinstance(result, str) or not result.strip():
            raise dg.Failure(
                description="Ollama returned an empty or invalid response payload.",
                metadata={
                    "model_name": self.model_name,
                    "base_url": self.base_url,
                    "response_body": json.dumps(body)[:500],
                },
            )

        return result.strip()

    def runtime_metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "llm_model": self.model_name,
            "ollama_base_url": self.base_url,
        }
        if self.runtime_dependency_package:
            metadata["runtime_dependency"] = self._distribution_string(
                self.runtime_dependency_package
            )
        return metadata

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise dg.Failure(
                description="Ollama returned an HTTP error while generating text.",
                metadata={
                    "model_name": self.model_name,
                    "base_url": self.base_url,
                    "status_code": exc.code,
                    "response_body": error_body[:500],
                },
            ) from exc
        except (OSError, TimeoutError, error.URLError) as exc:
            raise dg.Failure(
                description="Could not reach the local Ollama server.",
                metadata={
                    "model_name": self.model_name,
                    "base_url": self.base_url,
                    "error": str(exc),
                },
            ) from exc

        try:
            parsed = json.loads(raw_body)
        except ValueError as exc:
            raise dg.Failure(
                description="Ollama returned a non-JSON response.",
                metadata={
                    "model_name": self.model_name,
                    "base_url": self.base_url,
                    "response_body": raw_body[:500],
                },
            ) from exc

        if not isinstance(parsed, dict):
            raise dg.Failure(
                description="Ollama returned an unexpected response shape.",
                metadata={
                    "model_name": self.model_name,
                    "base_url": self.base_url,
                    "response_body": json.dumps(parsed)[:500],
                },
            )

        return parsed

    def _generate_with_lock(self, prompt: str) -> dict[str, Any]:
        lock_file = Path(self.lock_path)
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.lock_timeout_seconds

        with lock_file.open("a+", encoding="utf-8") as handle:
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                        raise
                    if time.monotonic() >= deadline:
                        raise dg.Failure(
                            description="Timed out waiting for the local Ollama request lock.",
                            metadata={
                                "model_name": self.model_name,
                                "lock_path": str(lock_file),
                                "lock_timeout_seconds": self.lock_timeout_seconds,
                            },
                        ) from exc
                    time.sleep(0.1)

            try:
                return self._post_json(
                    "/api/generate",
                    {
                        "model": self.model_name,
                        "system": self.system_prompt,
                        "prompt": prompt,
                        "stream": False,
                    },
                )
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _distribution_string(self, package_name: str) -> str:
        version = importlib_metadata.version(package_name)
        return f"{package_name}=={version}"


def build_llm_resource(
    resource_cls: type[OllamaLLMResource],
    *,
    model_env_var: str,
    default_model_name: str,
    runtime_dependency_package: str,
    legacy_model_env_var: str | None = None,
) -> OllamaLLMResource:
    return resource_cls(
        model_name=_get_str_env(
            model_env_var,
            default=default_model_name,
            legacy_name=legacy_model_env_var,
        ),
        base_url=_get_str_env(
            "OLLAMA_BASE_URL",
            default="http://localhost:11434",
        ),
        timeout_seconds=_get_float_env(
            "OLLAMA_TIMEOUT_SECONDS",
            default=300.0,
        ),
        lock_path=_get_str_env(
            "OLLAMA_LOCK_PATH",
            default="data/.ollama_generate.lock",
        ),
        lock_timeout_seconds=_get_float_env(
            "OLLAMA_LOCK_TIMEOUT_SECONDS",
            default=900.0,
        ),
        runtime_dependency_package=runtime_dependency_package,
    )


def _get_str_env(name: str, *, default: str, legacy_name: str | None = None) -> str:
    value = os.getenv(name)
    if value:
        return value

    if legacy_name:
        legacy_value = os.getenv(legacy_name)
        if legacy_value:
            return legacy_value

    return default


def _get_float_env(name: str, *, default: float, legacy_name: str | None = None) -> float:
    raw_value = os.getenv(name)
    source_name = name
    if not raw_value and legacy_name:
        raw_value = os.getenv(legacy_name)
        source_name = legacy_name

    if not raw_value:
        return default

    try:
        return float(raw_value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {source_name} must be a float.") from exc


class CatalogCoach(OllamaLLMResource):
    model_name: str = "qwen2.5:0.5b"
    system_prompt: str = (
        "You are a retail catalog editor. Improve copy and keep category labels tidy."
    )


class RiskReviewer(OllamaLLMResource):
    model_name: str = "qwen2.5:1.5b"
    system_prompt: str = (
        "You are a cautious fraud analyst. Provide concise reasoning for transaction risk."
    )


class BriefingWriter(OllamaLLMResource):
    model_name: str = "qwen2.5:0.5b"
    system_prompt: str = (
        "You summarize analytics for executives in a short and direct weekly briefing."
    )
