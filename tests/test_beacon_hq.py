from __future__ import annotations

from pathlib import Path

import dagster as dg

from shared.io_managers import make_duckdb_io_manager
from beacon_hq import defs
from beacon_hq.assets.reports import (
    briefing_highlights,
    consolidated_revenue,
    executive_context_packet,
    executive_llm_audit_log,
    executive_summary,
    risk_overview,
)
from tests.fakes import MockLLMResource


def test_beacon_hq_definitions_load() -> None:
    asset_keys = defs.resolve_all_asset_keys()
    assert dg.AssetKey(["beacon_hq", "executive_summary"]) in asset_keys
    assert dg.AssetKey(["beacon_hq", "consolidated_revenue"]) in asset_keys
    job_names = {job.name for job in defs.resolve_all_job_defs()}
    assert "beacon_reporting_inputs_job" in job_names
    assert "beacon_executive_briefing_job" in job_names
    sensor = defs.resolve_sensor_def("beacon_after_upstream_success_sensor")
    assert sensor.name == "beacon_after_upstream_success_sensor"


def test_beacon_hq_materializes(tmp_path: Path) -> None:
    result = dg.materialize(
        [
            consolidated_revenue,
            risk_overview,
            briefing_highlights,
            executive_context_packet,
            executive_summary,
            executive_llm_audit_log,
        ],
        resources={
            "llm": MockLLMResource(model_name="gamma-test"),
            "io_manager": make_duckdb_io_manager("beacon_hq_test", base_dir=tmp_path),
        },
    )
    assert result.success
    summary = result.output_for_node("executive_summary")
    assert "summary" in summary.columns
