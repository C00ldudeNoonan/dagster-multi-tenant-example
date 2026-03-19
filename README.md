# Multi-Tenant Dagster Webinar Demo

This repository contains a runnable local Dagster project that demonstrates:

- multi-tenant code locations
- context engineering as a data engineering workflow
- tenant-specific LLM resources

Start the local model server with Docker:

```bash
docker compose up -d ollama
./scripts/pull_ollama_models.sh
cp .env.example .env
set -a
source .env
set +a
```

Create one environment per code location:

```bash
./scripts/setup_code_location_envs.sh
```

Run the Dagster project locally with the root dev environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
export DAGSTER_HOME=$(pwd)/.dagster_home
mkdir -p "$DAGSTER_HOME"
python -m dagster dev -w workspace.yaml
```

Run validation locally with:

```bash
source .venv/bin/activate
set -a
source .env
set +a
export DAGSTER_HOME=$(pwd)/.dagster_home
mkdir -p "$DAGSTER_HOME"
ruff check .
pytest -q -o cache_dir=/tmp/pytest-cache
dg check defs
```

Each code location points at the same Ollama container but uses its own model selection:

- `harbor_outfitters`: `qwen2.5:0.5b`
- `summit_financial`: `qwen2.5:1.5b`
- `beacon_hq`: `qwen2.5:0.5b`

Local LLM requests are serialized through a shared lock file and use a longer default timeout so
the demo remains stable on smaller laptops and Docker allocations.

Each code location also uses its own Python environment and its own installed runtime marker
package/version:

- `harbor_outfitters`: `catalog_coach_runtime==1.4.0`
- `summit_financial`: `risk_reviewer_runtime==2.2.0`
- `beacon_hq`: `briefing_writer_runtime==0.9.0`

Assets are persisted to per-tenant DuckDB databases under `data/`.
