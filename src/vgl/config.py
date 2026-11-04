"""Configuration.

Everything the system needs from its environment, in one place, with defaults that
work for local development. Nothing else in the codebase reads os.environ directly.

Why it exists: so a reviewer can see every knob in thirty seconds, and so that
swapping a model or pointing at a different database is a one-line change that
never touches application code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load a local .env if present (Docker Compose injects env directly; this is for
# running outside the container). Never commit .env.
load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://vgl:vgl@localhost:5432/vgl"
    )

    # Language models. Composer writes the answer; judge checks faithfulness;
    # intake turns a question into a structured frame. Different models for
    # composer and judge is a deliberate independence choice.
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    composer_model: str = os.environ.get("VGL_COMPOSER_MODEL", "claude-opus-5-5")
    judge_model: str = os.environ.get("VGL_JUDGE_MODEL", "claude-sonnet-5-5")
    intake_model: str = os.environ.get("VGL_INTAKE_MODEL", "claude-sonnet-5-5")
    embed_model: str = os.environ.get("VGL_EMBED_MODEL", "text-embedding-3-small")
    # Truncated embedding dimension. Retrieval here is a recall problem over a small
    # corpus; 256 dimensions is plenty and keeps fixtures small.
    embed_dim: int = int(os.environ.get("VGL_EMBED_DIM", "256"))

    # live   — call the APIs
    # replay — serve recorded responses from fixtures; fail loudly if one is missing
    # record — call the APIs and save every response as a fixture
    llm_mode: str = os.environ.get("VGL_LLM_MODE", "live")
    fixtures_dir: Path = Path(
        os.environ.get("VGL_FIXTURES_DIR", REPO_ROOT / "tests" / "fixtures")
    )

    data_dir: Path = Path(os.environ.get("VGL_DATA_DIR", REPO_ROOT / "data"))
    demo_dir: Path = Path(os.environ.get("VGL_DEMO_DIR", REPO_ROOT / "demo"))

    # Closure traversal depth. Regulatory dependency chains are shallow by nature
    # (definition, interpretation, carve-out, annotation); four hops is generous.
    max_depth: int = int(os.environ.get("VGL_MAX_DEPTH", "4"))


settings = Settings()
