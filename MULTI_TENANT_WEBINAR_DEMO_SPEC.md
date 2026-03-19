# PROJECT SPEC: Multi-Tenant Dagster Webinar Demo

## Overview

Build a demo Dagster project for the Dagster Labs x Brooklyn Data "Multi-Tenancy for Modern Data Platforms" webinar. The project demonstrates multi-tenant architecture patterns using Dagster code locations, with a specific focus on AI/LLM model dependencies as swappable per-tenant resources and on context engineering as a first-class data engineering workflow.

Fork/extend the existing repo at `https://github.com/cnolanminich/multi-tenant-example` as the starting point. That repo already has the multi-code-location scaffolding with three subsidiaries, `workspace.yaml`, `dagster_cloud.yaml`, and a Dagster+ serverless deploy workflow.

## Goals

1. Show how Dagster code locations enable tenant isolation with independent dependencies
2. Demonstrate AI/ML models as swappable, per-tenant resources (the key differentiator David Gelman from Brooklyn Data requested)
3. Show that the real data engineering work is building curated context assets, not just calling an LLM
4. Provide a realistic medallion architecture (Bronze/Silver/Gold) that mirrors the Ida case study
5. Be runnable locally with `dagster dev -w workspace.yaml` using DuckDB (no cloud credentials required)
6. Be deployable to Dagster+ serverless for the live demo

## Existing Repo Structure to Preserve

The existing repo uses this pattern, which we keep:

```
workspace.yaml              # loads all three code locations
dagster_cloud.yaml          # Dagster+ serverless config for all three
setup.py / pyproject.toml   # single installable package
subsidiary_one/
  __init__.py               # re-exports defs
  assets.py
  definitions.py            # Definitions object
subsidiary_two/
  __init__.py
  assets.py
  definitions.py
subsidiary_three/
  __init__.py
  assets.py
  definitions.py
```

Key patterns from the existing code:
- Each subsidiary uses `key_prefix` and `group_name` matching its name
- Cross-tenant dependencies use `deps=[dg.AssetKey(["subsidiary_one", "accounts"])]`
- Each `definitions.py` exports a `Definitions` via `load_assets_from_modules`
- `__init__.py` re-exports as `from .definitions import defs`

## Proposed New Structure

Rename subsidiaries to more webinar-friendly tenant names. Each tenant represents a different client of a data consultancy (Brooklyn Data's perspective) with different data sources and AI model needs.

```
multi-tenant-webinar-demo/
├── workspace.yaml
├── dagster_cloud.yaml
├── pyproject.toml
├── setup.py
├── setup.cfg
├── README.md
├── shared/                          # Shared utilities across tenants
│   ├── __init__.py
│   ├── resources.py                 # LLM resource definitions (the swappable AI piece)
│   └── io_managers.py               # Shared DuckDB IO manager config
├── harbor_outfitters/               # Harbor Outfitters: Retail analytics client
│   ├── __init__.py
│   ├── definitions.py
│   ├── assets/
│   │   ├── __init__.py
│   │   ├── bronze.py                # Raw data ingestion
│   │   ├── silver.py                # Cleaned/standardized
│   │   └── gold.py                  # Context assembly + LLM outputs
│   └── resources.py                 # Tenant-specific resource config
├── summit_financial/                # Summit Financial: Financial services client
│   ├── __init__.py
│   ├── definitions.py
│   ├── assets/
│   │   ├── __init__.py
│   │   ├── bronze.py
│   │   ├── silver.py
│   │   └── gold.py
│   └── resources.py
├── beacon_hq/                       # Beacon HQ: Cross-tenant reporting
│   ├── __init__.py
│   ├── definitions.py
│   ├── assets/
│   │   ├── __init__.py
│   │   └── reports.py               # Depends on Alpha and Beta gold assets
│   └── resources.py
└── tests/
    ├── __init__.py
    ├── test_harbor_outfitters.py
    ├── test_summit_financial.py
    └── test_beacon_hq.py
```

## Detailed Implementation

### 1. shared/resources.py — The AI Swappable Dependency Pattern

This is the centerpiece of David's feedback. Define a shared local LLM resource backed by Ollama, then expose more relatable tenant-facing implementations with different prompts and default models.

```python
import dagster as dg
import json
from urllib import request

class OllamaLLMResource(dg.ConfigurableResource):
    """Shared local LLM client for all tenants."""
    model_name: str
    system_prompt: str
    base_url: str = "http://localhost:11434"

    def generate(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model_name,
                "system": self.system_prompt,
                "prompt": prompt,
                "stream": False,
            }
        ).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
        return str(body["response"]).strip()

class MockLLMResource(dg.ConfigurableResource):
    """Deterministic test double for unit tests and CI."""
    model_name: str = "mock-model"

    def generate(self, prompt: str) -> str:
        return f"[mock:{self.model_name}] {prompt[:80]}"

class CatalogCoach(OllamaLLMResource):
    """Retail copywriter and product taxonomy helper."""
    model_name: str = "mistral-nemo"
    system_prompt: str = (
        "You write short retail catalog copy and assign clean product categories."
    )

class RiskReviewer(OllamaLLMResource):
    """Transaction analyst that reviews suspicious financial activity."""
    model_name: str = "qwen2.5:7b"
    system_prompt: str = (
        "You are a cautious fraud analyst. Return concise risk reasoning and a risk level."
    )

class BriefingWriter(OllamaLLMResource):
    """Executive summary writer for cross-tenant reporting."""
    model_name: str = "mistral-nemo"
    system_prompt: str = (
        "You summarize analytics for executives in a short, direct briefing."
    )
```

Default local model plan:
- `CatalogCoach` uses `mistral-nemo`
- `RiskReviewer` uses `qwen2.5:7b`
- `BriefingWriter` uses `mistral-nemo`

Optional live-demo upgrade on stronger hardware:
- Upgrade `RiskReviewer` to `qwen2.5:14b`
- Upgrade `BriefingWriter` to `mistral-small3.1`

Add environment-variable overrides so the demo can downshift or upgrade models without code changes:
- `OLLAMA_BASE_URL`
- `TENANT_ALPHA_MODEL`
- `TENANT_BETA_MODEL`
- `TENANT_GAMMA_MODEL`

### Context Engineering Pattern Across All Tenants

The LLM should never operate on a raw table directly. Each tenant should follow the same pattern:

- **Bronze:** ingest raw business data plus reference documents, rules, examples, or taxonomies
- **Silver:** clean and standardize those sources into retrieval-ready context tables
- **Gold:** assemble a prompt input record from curated context, call the LLM, validate the response shape, and persist both the output and the prompt/context metadata

This keeps the demo focused on data engineering:
- Dagster assets build the context
- DuckDB stores the context tables and audit logs
- The LLM is one downstream consumer of structured context, not the main event

### 2. shared/io_managers.py — DuckDB IO Manager

Use DuckDB so the entire demo runs locally with zero cloud setup. Each tenant gets its own DuckDB database file for isolation.

```python
from dagster_duckdb_pandas import DuckDBPandasIOManager

def make_duckdb_io_manager(tenant_name: str) -> DuckDBPandasIOManager:
    return DuckDBPandasIOManager(
        database=f"data/{tenant_name}.duckdb",
        schema="main",
    )
```

### 3. harbor_outfitters/ — Retail Analytics (uses CatalogCoach on Mistral)

Simulates a retail client. The data engineering story is that Alpha curates catalog context before asking the model to write or classify anything.

**bronze.py:**
- `raw_sales` asset: Generates a pandas DataFrame of fake sales transactions (store_id, product_name, quantity, revenue, timestamp). Use `faker` or hardcoded sample data. ~1000 rows.
- `raw_products` asset: Generates a product catalog DataFrame (product_id, name, category, description).
- `raw_brand_guidelines` asset: Creates approved brand voice rules and banned phrases.
- `raw_taxonomy_examples` asset: Creates example product-to-category mappings for few-shot guidance.

**silver.py:**
- `cleaned_sales` asset: Depends on `raw_sales`. Standardizes column names, casts types, drops nulls, adds computed fields (e.g., revenue_per_unit).
- `standardized_products` asset: Depends on `raw_products`. Normalizes category names, deduplicates.
- `catalog_context_documents` asset: Combines standardized products, brand guidelines, and taxonomy examples into retrieval-ready context rows.
- `catalog_prompt_inputs` asset: Selects the best context per product and builds a prompt payload with product facts, approved examples, and style constraints.

**gold.py:**
- `enriched_products` asset: Depends on `catalog_prompt_inputs`. **Uses the LLM resource** to generate enriched product descriptions or category suggestions from curated context instead of raw text alone.
- `catalog_llm_audit_log` asset: Stores the prompt, selected context snippets, model name, and response for traceability.
- `sales_summary` asset: Depends on `cleaned_sales`. Aggregates by store and product category.

**resources.py / definitions.py:**
```python
# harbor_outfitters/definitions.py
defs = Definitions(
    assets=all_assets,
    resources={
        "llm": CatalogCoach(model_name="mistral-nemo"),
        "io_manager": make_duckdb_io_manager("harbor_outfitters"),
    },
)
```

### 4. summit_financial/ — Financial Services (uses RiskReviewer on Qwen)

Simulates a financial services client with stricter data governance. The data engineering story is that Beta assembles investigation context from rules, account history, and suspicious patterns before scoring risk.

**bronze.py:**
- `raw_transactions` asset: Generates fake financial transaction data (account_id, amount, type, merchant, timestamp).
- `raw_accounts` asset: Generates account metadata (account_id, customer_name, account_type, risk_tier).
- `raw_risk_rules` asset: Creates reference rules for suspicious merchants, amount thresholds, and escalation guidance.

**silver.py:**
- `cleaned_transactions` asset: Standardizes, validates amounts, flags suspicious entries.
- `validated_accounts` asset: Validates account data, ensures referential integrity.
- `transaction_context_windows` asset: Builds recent transaction windows and account-level summaries for each transaction under review.
- `risk_context_documents` asset: Joins cleaned transactions, account data, and risk rules into retrieval-ready investigation context.

**gold.py:**
- `risk_prompt_inputs` asset: Depends on `risk_context_documents`. Builds prompt payloads with the selected rules, recent history, and suspicious signals for each transaction.
- `transaction_risk_scores` asset: Depends on `risk_prompt_inputs`. **Uses the LLM resource** to generate risk assessments from structured context. The asset should request a structured response with fields like `risk_level`, `score`, and `rationale`.
- `risk_llm_audit_log` asset: Stores prompt inputs, retrieved context, model name, and parsed response for auditability.
- `account_summary` asset: Aggregated account-level metrics.

**definitions.py:**
```python
defs = Definitions(
    assets=all_assets,
    resources={
        "llm": RiskReviewer(model_name="qwen2.5:7b"),
        "io_manager": make_duckdb_io_manager("summit_financial"),
    },
)
```

### 5. beacon_hq/ — Cross-Tenant Reporting (uses BriefingWriter on Mistral)

Demonstrates cross-code-location dependencies. Consumes gold-layer assets from both Alpha and Beta to produce consolidated reports. Gamma should look like an analytics engineering team assembling briefing context from upstream tenant outputs.

**reports.py:**
- `consolidated_revenue` asset: Depends on `harbor_outfitters/sales_summary` via `deps=[dg.AssetKey(["harbor_outfitters", "sales_summary"])]`. For demo, it can read persisted summary outputs or generate a small derived table that mirrors the expected upstream shape.
- `risk_overview` asset: Depends on `summit_financial/account_summary` via cross-tenant dep.
- `executive_context_packet` asset: Depends on both above and assembles the KPI table, notable changes, and summary bullets that will be passed to the model.
- `executive_summary` asset: Depends on `executive_context_packet`. **Uses the LLM resource** to generate a natural language summary of the combined data.
- `executive_llm_audit_log` asset: Stores the context packet, model name, and generated briefing for demo traceability.

**definitions.py:**
```python
defs = Definitions(
    assets=all_assets,
    resources={
        "llm": BriefingWriter(model_name="mistral-nemo"),
        "io_manager": make_duckdb_io_manager("beacon_hq"),
    },
)
```

### 6. workspace.yaml

```yaml
load_from:
  - python_module:
      module_name: harbor_outfitters
  - python_module:
      module_name: summit_financial
  - python_module:
      module_name: beacon_hq
```

### 7. dagster_cloud.yaml

```yaml
locations:
  - location_name: harbor_outfitters
    code_source:
      package_name: harbor_outfitters
  - location_name: summit_financial
    code_source:
      package_name: summit_financial
  - location_name: beacon_hq
    code_source:
      package_name: beacon_hq
```

### 8. pyproject.toml

```toml
[project]
name = "multi-tenant-webinar-demo"
version = "0.1.0"
description = "Dagster multi-tenant demo with swappable AI dependencies and context engineering"
requires-python = ">=3.10,<3.13"
dependencies = [
    "dagster",
    "dagster-cloud",
    "dagster-duckdb-pandas",
    "pandas",
    "faker",
]

[project.optional-dependencies]
dev = [
    "dagster-webserver",
    "pytest",
]

[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[tool.dagster]
module_name = "harbor_outfitters.definitions"
code_location_name = "harbor_outfitters"
```

### 9. Tests

Each test file should:
- Test that assets can materialize using `dg.materialize`
- Test with `MockLLMResource` so CI does not depend on local Ollama
- Verify the resource swapping pattern works (same asset code, different resource config)
- Verify that context assembly assets produce the expected prompt payload shape before the LLM step runs
- For Beta, validate that structured model outputs can be parsed into stable columns

Example pattern:
```python
def test_enriched_products():
    from harbor_outfitters.assets.gold import enriched_products
    from shared.resources import MockLLMResource

    # Test that we can swap in a deterministic test resource
    result = dg.materialize(
        [enriched_products],
        resources={
            "llm": MockLLMResource(model_name="test-model"),
            "io_manager": ...,
        },
    )
    assert result.success
```

### 10. README.md

Write a clear README with:
- What this project demonstrates (multi-tenancy + context engineering + AI dependency swapping)
- Architecture diagram (can be mermaid in markdown)
- How to run locally (`pip install -e ".[dev]"` then `dagster dev -w workspace.yaml`)
- How to install and pull the local open models with Ollama
- Explanation of the three tenants and their different AI model configs
- Explanation of the shared context engineering pattern: raw sources -> curated context tables -> prompt inputs -> LLM outputs -> audit logs
- Link to the webinar abstract/recording (placeholder)

## Key Demo Talking Points This Enables

1. **Context engineering, not prompt hacking:** The core Dagster job is building the right context tables and prompt inputs. The LLM call is just one downstream asset.

2. **Same interface, different local models:** All three tenants use `context.resources.llm.generate(prompt)` but get different open models and prompts through the same Ollama-backed resource interface. Show this in the Dagster UI resource configuration view.

3. **Tenant isolation:** Each code location has its own DuckDB database, its own resources, its own dependency graph. Show the asset graph filtered by code location in the UI.

4. **Cross-tenant dependencies:** Tenant Gamma depends on gold-layer outputs from Alpha and Beta. Show the cross-code-location lineage in the global asset graph.

5. **Medallion architecture:** Bronze/Silver/Gold layers visible as asset groups within each tenant. Bronze holds raw operational data and reference data, Silver holds curated context, and Gold holds prompt inputs, outputs, and business summaries.

6. **Auditability:** Persisting context packets and LLM audit logs makes the AI step inspectable in the same way as any other data asset.

7. **Testing with resource swapping:** Show how the same pipeline can be tested with `MockLLMResource`, then run locally with real open models. The Dagster resource system makes this trivial.

## What NOT to Build

- No hosted API dependencies. The demo should use local Ollama for real open-model inference and `MockLLMResource` for tests.
- No Kubernetes deployment config. The webinar will talk about K8s patterns conceptually (RBC Borealis), but the demo stays on Dagster+ serverless and local dev.
- No dbt integration in this demo. The Ida case study covers dbt multi-tenancy; this demo focuses on the Dagster-native code location + resource pattern. Keep it simple.
- No real data sources. All data is generated in-process with faker or hardcoded DataFrames.
- No vector database for v1. Retrieval can be deterministic and DuckDB-backed so the context engineering story stays simple and clearly data-engineering-oriented.

## Definition of Done

- [ ] `dagster dev -w workspace.yaml` launches and shows three code locations in the UI
- [ ] Each tenant's asset graph renders correctly with Bronze/Silver/Gold grouping
- [ ] Each tenant has visible context-engineering assets upstream of the LLM call
- [ ] Materializing all assets in each tenant succeeds locally with Ollama running
- [ ] Cross-tenant dependencies from Gamma to Alpha/Beta are visible in the global asset graph
- [ ] Resource config in the UI shows different LLM models per tenant
- [ ] Audit-log assets capture prompt/context/model metadata for each tenant
- [ ] `pytest tests/` passes
- [ ] README explains the architecture and how to run
- [ ] `dagster_cloud.yaml` is valid for serverless deployment
