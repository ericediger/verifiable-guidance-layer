# Verifiable Guidance Layer — application image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY pyproject.toml ./
RUN mkdir -p src/vgl && touch src/vgl/__init__.py \
 && pip install --quiet -e ".[dev]"

COPY src ./src
COPY data ./data
COPY demo ./demo
COPY tests ./tests
COPY docs ./docs
COPY README.md CLAUDE.md ./

EXPOSE 8000
CMD ["uvicorn", "vgl.api:app", "--host", "0.0.0.0", "--port", "8000"]
