"""The one door to the language models.

Every call to Anthropic (composition, judging, intake) or OpenAI (embeddings) goes
through this module, in one of three modes:

    live    call the API
    replay  serve the recorded response for an identical request; fail loudly if none
    record  call the API and save the response as a fixture

Why it exists: probabilistic components cannot be unit-tested by exact string match,
and a test suite that needs network and spends money on every run is one nobody runs.
Recording lets the evals be deterministic in CI and reproducible in a demo, while a
single flag (`--live`) runs the same evals against the real models.

Nothing in `closure.py` or `verify.py` imports this module. That is a rule, not a habit:
the deterministic core must not be able to call a model even by accident.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vgl.config import settings


class FixtureMissing(RuntimeError):
    """Raised in replay mode when no recording exists for a request."""


def _key(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


@dataclass
class LLM:
    mode: str = field(default_factory=lambda: settings.llm_mode)
    fixtures_dir: Path = field(default_factory=lambda: Path(settings.fixtures_dir))
    embed_model: str = field(default_factory=lambda: settings.embed_model)
    embed_dim: int = field(default_factory=lambda: settings.embed_dim)

    def __post_init__(self) -> None:
        if self.mode not in {"live", "replay", "record"}:
            raise ValueError(f"unknown VGL_LLM_MODE {self.mode!r}")
        self._anthropic = None
        self._openai = None
        self._embed_cache: dict[str, list[float]] | None = None

    # ── fixtures ────────────────────────────────────────────────────────────────

    @property
    def _completions_dir(self) -> Path:
        return self.fixtures_dir / "llm"

    @property
    def _embeddings_file(self) -> Path:
        return self.fixtures_dir / "embeddings.json"

    def _load_embed_cache(self) -> dict[str, list[float]]:
        if self._embed_cache is None:
            if self._embeddings_file.exists():
                self._embed_cache = json.loads(self._embeddings_file.read_text())
            else:
                self._embed_cache = {}
        return self._embed_cache

    def _save_embed_cache(self) -> None:
        self._embeddings_file.parent.mkdir(parents=True, exist_ok=True)
        self._embeddings_file.write_text(json.dumps(self._load_embed_cache(), separators=(",", ":")))

    # ── embeddings ──────────────────────────────────────────────────────────────

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts. Results are cached by (model, dim, text) in all modes."""
        cache = self._load_embed_cache()
        keys = [_key({"m": self.embed_model, "d": self.embed_dim, "t": t}) for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts) if k not in cache]

        if missing:
            if self.mode == "replay":
                raise FixtureMissing(
                    f"{len(missing)} embedding(s) not recorded; run with --record. "
                    f"First missing text: {missing[0][1][:80]!r}"
                )
            vectors = self._embed_live([t for _, t in missing])
            for (k, _), v in zip(missing, vectors):
                cache[k] = v
            # Save in record mode and in live mode alike: a live run that has already
            # paid for an embedding should not pay again.
            self._save_embed_cache()

        return [cache[k] for k in keys]

    def _embed_live(self, texts: list[str]) -> list[list[float]]:
        if self._openai is None:
            from openai import OpenAI

            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is not set and no fixture exists")
            self._openai = OpenAI(api_key=settings.openai_api_key)
        out: list[list[float]] = []
        # The API accepts batches; keep them modest.
        for i in range(0, len(texts), 64):
            batch = texts[i : i + 64]
            resp = self._openai.embeddings.create(
                model=self.embed_model, input=batch, dimensions=self.embed_dim
            )
            out.extend([d.embedding for d in resp.data])
        return out

    # ── structured completions ─────────────────────────────────────────────────

    def complete_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Ask a model for a JSON object conforming to `schema`.

        Uses the API's native structured outputs, so the response conforms to the
        schema by construction. Determinism across runs comes from record/replay and
        from the verifier downstream, not from the model.
        """
        request = {
            "provider": "anthropic",
            "model": model,
            "system": system,
            "user": user,
            "schema_name": schema_name,
            "schema": schema,
            "max_tokens": max_tokens,
        }
        key = _key(request)
        path = self._completions_dir / f"{schema_name}-{key}.json"

        if self.mode in {"replay", "record"} and path.exists():
            return json.loads(path.read_text())["response"]
        if self.mode == "replay":
            raise FixtureMissing(f"no recording for {schema_name} ({key}); run with --record")

        response = self._complete_json_live(request)
        if self.mode == "record":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"request": request, "response": response}, indent=2, ensure_ascii=False))
        return response

    def _complete_json_live(self, request: dict[str, Any]) -> dict[str, Any]:
        if self._anthropic is None:
            from anthropic import Anthropic

            if not settings.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set and no fixture exists")
            self._anthropic = Anthropic(api_key=settings.anthropic_api_key)

        # Native structured outputs: the API enforces the schema, so the response is
        # valid JSON of the requested shape by construction.
        resp = self._anthropic.messages.create(
            model=request["model"],
            max_tokens=request["max_tokens"],
            system=request["system"],
            messages=[{"role": "user", "content": request["user"]}],
            output_config={"format": {"type": "json_schema", "schema": request["schema"]}},
        )
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        if not text:
            raise RuntimeError(f"model returned no text (stop_reason={resp.stop_reason})")
        return json.loads(text)


# A module-level default so callers can simply `from vgl.llm import llm`.
llm = LLM()
