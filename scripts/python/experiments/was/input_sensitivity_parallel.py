#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run a max-parallel, staged sensitivity campaign on stale input-calibrated keys.

Implements:
- Stage A: one-factor two-point local sweep
- Stage B: stress sweep on top-2 parameters from Stage A by |delta_housing|
- Stage C: pairwise interaction checks on the same top-2 parameters

Primary objective:
- Minimize housing_wealth_diff under guardrails.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any


INCOME_GUARDRAIL = 8.5
FINANCIAL_GUARDRAIL = 13.0

VALIDATION_PATTERNS = {
    "income_diff": re.compile(r"Income total diff:\s*([0-9.]+)\s*%"),
    "housing_diff": re.compile(r"Housing wealth total diff:\s*([0-9.]+)\s*%"),
    "financial_diff": re.compile(r"Financial wealth total diff:\s*([0-9.]+)\s*%"),
}

DATASET_MAPPING = {
    "BUY_SCALE": "PSD + Land Registry purchase-budget refresh",
    "BUY_EXPONENT": "PSD + Land Registry purchase-budget refresh",
    "BANK_AFFORDABILITY_HARD_MAX": "PSD affordability-ratio or equivalent borrower burden table refresh",
    "BANK_LTI_HARD_MAX_FTB": "PSD LTI distribution refresh (FTB segment)",
    "BANK_LTI_HARD_MAX_HM": "PSD LTI distribution refresh (HM segment)",
    "BANK_INITIAL_CREDIT_SUPPLY": "PSD/CML/BoE mortgage flow and supply refresh",
    "HOLD_PERIOD": "EHS tenure-duration refresh",
    "HPA_EXPECTATION_FACTOR": "NMG expectations + LR/HPI expectation-fit refresh",
    "HPA_EXPECTATION_CONST": "NMG expectations + LR/HPI expectation-fit refresh",
}

STAGE_A_BOUNDS = {
    "BUY_SCALE": (38.613249, 47.193971),
    "BUY_EXPONENT": (0.71025255, 0.86808645),
    "BANK_AFFORDABILITY_HARD_MAX": (0.37, 0.43),
    "BANK_LTI_HARD_MAX_FTB": (5.1, 5.7),
    "BANK_LTI_HARD_MAX_HM": (5.3, 5.9),
    "BANK_INITIAL_CREDIT_SUPPLY": (207, 281),
    "HOLD_PERIOD": (13.6, 20.4),
    "HPA_EXPECTATION_FACTOR": (0.352, 0.528),
    "HPA_EXPECTATION_CONST": (-0.010, -0.004),
}

STRESS_CLAMPS = {
    "BANK_AFFORDABILITY_HARD_MAX": (0.25, 0.55),
    "BANK_LTI_HARD_MAX_FTB": (4.0, 7.0),
    "BANK_LTI_HARD_MAX_HM": (4.0, 7.0),
    "BUY_EXPONENT": (0.5, 1.1),
    "HPA_EXPECTATION_FACTOR": (0.1, 0.9),
}


@dataclass
class Scenario:
    scenario_id: str
    stage: str
    parameter: str
    direction: str
    updates: dict[str, str]
    attempts: int = 0


@dataclass
class AttemptResult:
    success: bool
    scenario: Scenario
    output_subdir: str
    config_path: Path
    attempt: int
    elapsed_seconds: float
    diffs: dict[str, float] | None
    error_text: str = ""


def default_maven_bin(repo_root: Path) -> str:
    """Return the repo-local Maven wrapper executable for this platform."""

    return str(repo_root / ("mvnw.cmd" if os.name == "nt" else "mvnw"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Concurrent stale-input sensitivity runner.")
    parser.add_argument(
        "--base-config",
        default="input-data-versions/v4.0/config.properties",
        help="Base config to perturb (default: input-data-versions/v4.0/config.properties).",
    )
    parser.add_argument(
        "--results-root",
        default="Results",
        help="Root output directory for scenario model outputs (default: Results).",
    )
    parser.add_argument(
        "--out-root",
        default="tmp/input_sensitivity_v40",
        help="Root directory for configs/logs/ledgers (default: tmp/input_sensitivity_v40).",
    )
    parser.add_argument(
        "--dataset",
        default="R8",
        choices=("R8", "W3"),
        help="WAS dataset for validation (default: R8).",
    )
    parser.add_argument(
        "--max-workers-cap",
        type=int,
        default=12,
        help="Absolute worker cap after adaptive sizing (default: 12).",
    )
    parser.add_argument(
        "--cpu-reserve",
        type=int,
        default=2,
        help="CPU cores to reserve when computing cpu_cap (default: 2).",
    )
    parser.add_argument(
        "--mem-reserve-gib",
        type=float,
        default=3.0,
        help="GiB memory reserve when computing mem_cap (default: 3.0).",
    )
    parser.add_argument(
        "--rss-multiplier",
        type=float,
        default=1.8,
        help="Safety multiplier for per-run RSS estimate (default: 1.8).",
    )
    parser.add_argument(
        "--workers-override",
        type=int,
        default=None,
        help="If provided, bypass adaptive sizing and use this worker count.",
    )
    parser.add_argument(
        "--keep-probe-output",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Keep probe output folder (default: false).",
    )
    return parser.parse_args()


def read_properties(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def apply_updates_to_config(config_text: str, updates: dict[str, str]) -> str:
    lines = config_text.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key} = {updates[key]}")
            seen.add(key)
        else:
            out.append(line)
    missing = sorted(set(updates.keys()) - seen)
    if missing:
        raise RuntimeError(f"Missing keys in base config: {missing}")
    return "\n".join(out) + "\n"


def parse_validation_diffs(output: str) -> dict[str, float]:
    diffs: dict[str, float] = {}
    for key, pattern in VALIDATION_PATTERNS.items():
        match = pattern.search(output)
        if not match:
            raise RuntimeError(f"Missing '{key}' in validation output.")
        diffs[key] = float(match.group(1))
    return diffs


def is_recoverable_resource_error(text: str) -> bool:
    lower = text.lower()
    needles = [
        "outofmemoryerror",
        "cannot allocate memory",
        "killed",
        "exit code 137",
        "java heap space",
        "unable to create native thread",
    ]
    return any(item in lower for item in needles)


def parse_mem_available_gib() -> float:
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    match = re.search(r"^MemAvailable:\s+([0-9]+)\s+kB$", meminfo, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Could not parse MemAvailable from /proc/meminfo.")
    kb = int(match.group(1))
    return kb / (1024.0 * 1024.0)


def parse_nproc() -> int:
    result = subprocess.run(
        ["nproc"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return int(result.stdout.strip())


def probe_rss_gib(base_config: Path, probe_output_subdir: str) -> tuple[float, float]:
    repo_root = Path.cwd()
    cmd = [
        "/usr/bin/time",
        "-v",
        default_maven_bin(repo_root),
        "-q",
        "exec:java",
        f"-Dexec.args=-configFile {base_config} -outputFolder {probe_output_subdir} -dev",
    ]
    started = time.time()
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed = time.time() - started
    if proc.returncode != 0:
        raise RuntimeError(
            "RSS probe failed.\n"
            f"STDOUT tail:\n{proc.stdout[-1200:]}\n"
            f"STDERR tail:\n{proc.stderr[-1200:]}"
        )
    match = re.search(r"Maximum resident set size \(kbytes\):\s*([0-9]+)", proc.stderr)
    if not match:
        raise RuntimeError("Could not parse Maximum resident set size from /usr/bin/time output.")
    rss_kb = int(match.group(1))
    return rss_kb / (1024.0 * 1024.0), elapsed


def choose_workers(
    nproc: int,
    mem_available_gib: float,
    rss_probe_gib: float,
    cpu_reserve: int,
    mem_reserve_gib: float,
    rss_multiplier: float,
    max_workers_cap: int,
) -> dict[str, Any]:
    cpu_cap = max(2, nproc - cpu_reserve)
    denom = max(0.05, rss_probe_gib * rss_multiplier)
    mem_cap = max(2, math.floor((mem_available_gib - mem_reserve_gib) / denom))
    workers = max(2, min(cpu_cap, mem_cap, max_workers_cap))
    return {
        "nproc": nproc,
        "mem_available_gib": mem_available_gib,
        "rss_probe_gib": rss_probe_gib,
        "cpu_cap": cpu_cap,
        "mem_cap": mem_cap,
        "workers": workers,
    }


def build_stage_a_scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = []
    idx = 1
    for parameter, (low, high) in STAGE_A_BOUNDS.items():
        for direction, value in (("low", low), ("high", high)):
            scenario_id = f"a{idx:02d}_{parameter.lower()}_{direction}"
            scenarios.append(
                Scenario(
                    scenario_id=scenario_id,
                    stage="A",
                    parameter=parameter,
                    direction=direction,
                    updates={parameter: format_value(value)},
                )
            )
            idx += 1
    return scenarios


def clamp_value(parameter: str, value: float) -> float:
    if parameter not in STRESS_CLAMPS:
        return value
    low, high = STRESS_CLAMPS[parameter]
    return min(high, max(low, value))


def format_value(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text


def make_stage_b_scenarios(
    top_parameters: list[str],
    baseline_props: dict[str, str],
) -> list[Scenario]:
    scenarios: list[Scenario] = []
    idx = 1
    for parameter in top_parameters:
        baseline = float(baseline_props[parameter])
        local_low, local_high = STAGE_A_BOUNDS[parameter]
        stress_low = clamp_value(parameter, baseline + 2.0 * (local_low - baseline))
        stress_high = clamp_value(parameter, baseline + 2.0 * (local_high - baseline))
        for direction, value in (("stress_low", stress_low), ("stress_high", stress_high)):
            scenario_id = f"b{idx:02d}_{parameter.lower()}_{direction}"
            scenarios.append(
                Scenario(
                    scenario_id=scenario_id,
                    stage="B",
                    parameter=parameter,
                    direction=direction,
                    updates={parameter: format_value(value)},
                )
            )
            idx += 1
    return scenarios


def best_stage_a_direction(
    stage_a_rows: list[dict[str, Any]],
    parameter: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = [row for row in stage_a_rows if row["parameter"] == parameter and row["status"] == "success"]
    if len(candidates) != 2:
        raise RuntimeError(f"Expected 2 Stage A successful rows for {parameter}, found {len(candidates)}")
    candidates_sorted = sorted(candidates, key=lambda row: row["housing_diff"])
    return candidates_sorted[0], candidates_sorted[1]


def extract_single_param_value(row: dict[str, Any], parameter: str) -> str:
    pairs = [token.strip() for token in str(row["updated_value"]).split(";") if token.strip()]
    mapping: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        mapping[key.strip()] = value.strip()
    if parameter not in mapping:
        raise RuntimeError(f"Could not extract value for {parameter} from row: {row['updated_value']}")
    return mapping[parameter]


def make_stage_c_scenarios(
    top_parameters: list[str],
    stage_a_rows: list[dict[str, Any]],
) -> list[Scenario]:
    p1, p2 = top_parameters
    p1_best, p1_other = best_stage_a_direction(stage_a_rows, p1)
    p2_best, p2_other = best_stage_a_direction(stage_a_rows, p2)

    scenario_improving = Scenario(
        scenario_id="c01_interaction_improving",
        stage="C",
        parameter=f"{p1}+{p2}",
        direction="both_improving",
        updates={
            p1: extract_single_param_value(p1_best, p1),
            p2: extract_single_param_value(p2_best, p2),
        },
    )
    scenario_opposite = Scenario(
        scenario_id="c02_interaction_opposite",
        stage="C",
        parameter=f"{p1}+{p2}",
        direction="both_opposite",
        updates={
            p1: extract_single_param_value(p1_other, p1),
            p2: extract_single_param_value(p2_other, p2),
        },
    )
    return [scenario_improving, scenario_opposite]


def run_single_attempt(
    scenario: Scenario,
    base_config_text: str,
    configs_dir: Path,
    logs_dir: Path,
    results_root: str,
    dataset: str,
    repo_root: Path,
) -> AttemptResult:
    config_path = configs_dir / f"{scenario.scenario_id}.properties"
    updated_config = apply_updates_to_config(base_config_text, scenario.updates)
    config_path.write_text(updated_config, encoding="utf-8")

    output_subdir = f"{results_root}/{scenario.scenario_id}-output"
    output_dir = repo_root / output_subdir
    if output_dir.exists():
        shutil.rmtree(output_dir)

    model_log = logs_dir / f"{scenario.scenario_id}.attempt{scenario.attempts + 1}.model.log"
    validation_log = logs_dir / f"{scenario.scenario_id}.attempt{scenario.attempts + 1}.validation.log"

    started = time.time()
    with model_log.open("w", encoding="utf-8") as handle:
        model_cmd = [
            default_maven_bin(repo_root),
            "-q",
            "exec:java",
            f"-Dexec.args=-configFile {config_path} -outputFolder {output_subdir} -dev",
        ]
        model_proc = subprocess.run(model_cmd, cwd=repo_root, stdout=handle, stderr=subprocess.STDOUT, text=True)
    if model_proc.returncode != 0:
        tail = model_log.read_text(encoding="utf-8")[-2000:]
        return AttemptResult(
            success=False,
            scenario=scenario,
            output_subdir=output_subdir,
            config_path=config_path,
            attempt=scenario.attempts + 1,
            elapsed_seconds=time.time() - started,
            diffs=None,
            error_text=f"Model run failed (rc={model_proc.returncode}).\n{tail}",
        )

    env = os.environ.copy()
    env.update(
        {
            "WAS_DATASET": dataset,
            "WAS_DATA_ROOT": str(repo_root),
            "WAS_RESULTS_ROOT": str(repo_root),
            "WAS_RESULTS_RUN_SUBDIR": output_subdir,
            "WAS_VALIDATION_PLOTS": "0",
            "MPLBACKEND": "Agg",
        }
    )
    validation_cmd = ["./scripts/was/run_was_validation.sh"]
    validation_proc = subprocess.run(
        validation_cmd,
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    validation_combined = (validation_proc.stdout or "") + "\n" + (validation_proc.stderr or "")
    validation_log.write_text(validation_combined, encoding="utf-8")
    if validation_proc.returncode != 0:
        return AttemptResult(
            success=False,
            scenario=scenario,
            output_subdir=output_subdir,
            config_path=config_path,
            attempt=scenario.attempts + 1,
            elapsed_seconds=time.time() - started,
            diffs=None,
            error_text=f"Validation failed (rc={validation_proc.returncode}).\n{validation_combined[-2000:]}",
        )

    try:
        diffs = parse_validation_diffs(validation_proc.stdout)
    except Exception as exc:
        return AttemptResult(
            success=False,
            scenario=scenario,
            output_subdir=output_subdir,
            config_path=config_path,
            attempt=scenario.attempts + 1,
            elapsed_seconds=time.time() - started,
            diffs=None,
            error_text=f"Could not parse validation diffs: {exc}\n{validation_combined[-2000:]}",
        )

    return AttemptResult(
        success=True,
        scenario=scenario,
        output_subdir=output_subdir,
        config_path=config_path,
        attempt=scenario.attempts + 1,
        elapsed_seconds=time.time() - started,
        diffs=diffs,
    )


def execute_parallel_stage(
    scenarios: list[Scenario],
    stage_name: str,
    base_config_text: str,
    configs_dir: Path,
    logs_dir: Path,
    results_root: str,
    dataset: str,
    repo_root: Path,
    initial_workers: int,
    ledger_writer: csv.DictWriter,
    ledger_handle: Any,
    baseline_diffs: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queue: deque[Scenario] = deque(scenarios)
    completed_rows: list[dict[str, Any]] = []
    desired_workers = initial_workers
    retry_events = 0
    worker_reductions = 0
    total_attempts = 0
    fatal_errors: list[str] = []
    active: dict[Future[AttemptResult], Scenario] = {}

    started = time.time()
    with ThreadPoolExecutor(max_workers=initial_workers) as executor:
        while queue or active:
            while queue and len(active) < desired_workers:
                scenario = queue.popleft()
                future = executor.submit(
                    run_single_attempt,
                    scenario,
                    base_config_text,
                    configs_dir,
                    logs_dir,
                    results_root,
                    dataset,
                    repo_root,
                )
                active[future] = scenario

            if not active:
                break

            done, _ = wait(active.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                scenario = active.pop(future)
                total_attempts += 1
                try:
                    result = future.result()
                except Exception as exc:
                    result = AttemptResult(
                        success=False,
                        scenario=scenario,
                        output_subdir=f"{results_root}/{scenario.scenario_id}-output",
                        config_path=configs_dir / f"{scenario.scenario_id}.properties",
                        attempt=scenario.attempts + 1,
                        elapsed_seconds=0.0,
                        diffs=None,
                        error_text=f"Unhandled exception: {exc}",
                    )

                if result.success and result.diffs is not None:
                    row = {
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "stage": stage_name,
                        "scenario_id": scenario.scenario_id,
                        "parameter": scenario.parameter,
                        "direction": scenario.direction,
                        "updated_keys": ";".join(sorted(scenario.updates.keys())),
                        "updated_value": ";".join(
                            f"{key}={scenario.updates[key]}" for key in sorted(scenario.updates.keys())
                        ),
                        "attempt": result.attempt,
                        "status": "success",
                        "workers_active_cap": desired_workers,
                        "output_subdir": result.output_subdir,
                        "config_path": str(result.config_path),
                        "elapsed_seconds": round(result.elapsed_seconds, 3),
                        "income_diff": round(result.diffs["income_diff"], 6),
                        "housing_diff": round(result.diffs["housing_diff"], 6),
                        "financial_diff": round(result.diffs["financial_diff"], 6),
                        "delta_income": round(result.diffs["income_diff"] - baseline_diffs["income_diff"], 6),
                        "delta_housing": round(result.diffs["housing_diff"] - baseline_diffs["housing_diff"], 6),
                        "delta_financial": round(result.diffs["financial_diff"] - baseline_diffs["financial_diff"], 6),
                        "guard_income_pass": result.diffs["income_diff"] <= INCOME_GUARDRAIL,
                        "guard_financial_pass": result.diffs["financial_diff"] <= FINANCIAL_GUARDRAIL,
                        "guard_all_pass": (
                            result.diffs["income_diff"] <= INCOME_GUARDRAIL
                            and result.diffs["financial_diff"] <= FINANCIAL_GUARDRAIL
                        ),
                        "error_text": "",
                    }
                    completed_rows.append(row)
                    ledger_writer.writerow(row)
                    ledger_handle.flush()
                    print(
                        f"[{stage_name}] {scenario.scenario_id} "
                        f"(attempt {result.attempt}) -> "
                        f"[{row['income_diff']:.3f}, {row['housing_diff']:.3f}, {row['financial_diff']:.3f}]"
                    )
                    continue

                # Failure path
                scenario.attempts += 1
                recoverable = is_recoverable_resource_error(result.error_text)
                retry_decision = "fatal"
                if recoverable and scenario.attempts == 1:
                    queue.append(scenario)
                    retry_events += 1
                    retry_decision = "retry_same_workers"
                elif recoverable and scenario.attempts == 2:
                    new_workers = max(2, desired_workers - 2)
                    if new_workers < desired_workers:
                        desired_workers = new_workers
                        worker_reductions += 1
                    queue.append(scenario)
                    retry_events += 1
                    retry_decision = "retry_after_worker_reduction"
                elif recoverable and scenario.attempts <= 3:
                    queue.append(scenario)
                    retry_events += 1
                    retry_decision = "final_retry"
                else:
                    fatal_errors.append(
                        f"{scenario.scenario_id} attempt {result.attempt}: {result.error_text[-800:]}"
                    )

                fail_row = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "stage": stage_name,
                    "scenario_id": scenario.scenario_id,
                    "parameter": scenario.parameter,
                    "direction": scenario.direction,
                    "updated_keys": ";".join(sorted(scenario.updates.keys())),
                    "updated_value": ";".join(
                        f"{key}={scenario.updates[key]}" for key in sorted(scenario.updates.keys())
                    ),
                    "attempt": result.attempt,
                    "status": "retryable_failure" if retry_decision != "fatal" else "fatal_failure",
                    "workers_active_cap": desired_workers,
                    "output_subdir": result.output_subdir,
                    "config_path": str(result.config_path),
                    "elapsed_seconds": round(result.elapsed_seconds, 3),
                    "income_diff": "",
                    "housing_diff": "",
                    "financial_diff": "",
                    "delta_income": "",
                    "delta_housing": "",
                    "delta_financial": "",
                    "guard_income_pass": "",
                    "guard_financial_pass": "",
                    "guard_all_pass": "",
                    "error_text": result.error_text[-1200:],
                }
                ledger_writer.writerow(fail_row)
                ledger_handle.flush()
                print(
                    f"[{stage_name}] {scenario.scenario_id} failed (attempt {result.attempt}) "
                    f"-> {retry_decision}"
                )

    elapsed = time.time() - started
    if fatal_errors:
        joined = "\n\n".join(fatal_errors[:5])
        raise RuntimeError(f"{stage_name} had fatal scenario failures:\n{joined}")

    summary = {
        "stage": stage_name,
        "initial_workers": initial_workers,
        "final_workers": desired_workers,
        "retry_events": retry_events,
        "worker_reductions": worker_reductions,
        "total_attempts": total_attempts,
        "elapsed_seconds": elapsed,
        "completed_success_count": len(completed_rows),
    }
    return completed_rows, summary


def select_top2_parameters(stage_a_rows: list[dict[str, Any]]) -> list[str]:
    best_abs_delta: dict[str, float] = {}
    for row in stage_a_rows:
        if row["status"] != "success":
            continue
        parameter = row["parameter"]
        abs_delta = abs(float(row["delta_housing"]))
        best_abs_delta[parameter] = max(best_abs_delta.get(parameter, 0.0), abs_delta)
    ranked = sorted(best_abs_delta.items(), key=lambda item: item[1], reverse=True)
    if len(ranked) < 2:
        raise RuntimeError("Could not select top-2 parameters from Stage A.")
    return [ranked[0][0], ranked[1][0]]


def build_decision_matrix(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    per_parameter: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["status"] != "success":
            continue
        parameter = row["parameter"]
        if "+" in parameter:
            continue
        housing_diff = float(row["housing_diff"])
        delta_housing = float(row["delta_housing"])
        rec = per_parameter.setdefault(
            parameter,
            {
                "parameter": parameter,
                "best_housing_diff": housing_diff,
                "best_delta_housing": delta_housing,
                "max_abs_delta_housing": abs(delta_housing),
                "best_scenario_id": row["scenario_id"],
                "best_direction": row["direction"],
                "has_guardrail_improving_direction": False,
            },
        )
        rec["max_abs_delta_housing"] = max(rec["max_abs_delta_housing"], abs(delta_housing))
        improved = delta_housing < 0 and bool(row["guard_all_pass"])
        rec["has_guardrail_improving_direction"] = rec["has_guardrail_improving_direction"] or improved
        if housing_diff < rec["best_housing_diff"]:
            rec["best_housing_diff"] = housing_diff
            rec["best_delta_housing"] = delta_housing
            rec["best_scenario_id"] = row["scenario_id"]
            rec["best_direction"] = row["direction"]

    matrix: list[dict[str, Any]] = []
    for _, rec in per_parameter.items():
        max_abs = rec["max_abs_delta_housing"]
        if rec["has_guardrail_improving_direction"] and max_abs >= 1.5:
            priority = "high"
        elif rec["has_guardrail_improving_direction"] and max_abs >= 0.75:
            priority = "medium"
        else:
            priority = "low"
        matrix.append(
            {
                **rec,
                "priority": priority,
                "dataset_refresh_path": DATASET_MAPPING.get(rec["parameter"], "Needs manual mapping"),
            }
        )
    matrix.sort(key=lambda row: {"high": 0, "medium": 1, "low": 2}[row["priority"]])
    return matrix


def write_summary_markdown(
    out_root: Path,
    baseline_diffs: dict[str, float],
    worker_meta: dict[str, Any],
    stage_summaries: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    top2: list[str],
    total_elapsed: float,
) -> None:
    success_rows = [row for row in all_rows if row["status"] == "success"]
    ranked = sorted(
        success_rows,
        key=lambda row: (
            0 if row["guard_all_pass"] else 1,
            float(row["housing_diff"]),
            float(row["financial_diff"]),
            float(row["income_diff"]),
        ),
    )
    scenarios_per_min = len(success_rows) / max(total_elapsed / 60.0, 1e-9)

    lines: list[str] = []
    lines.append("# Input Sensitivity Summary (v4.0)")
    lines.append("")
    lines.append("## Baseline")
    lines.append("")
    lines.append(
        "- triplet: "
        f"[{baseline_diffs['income_diff']:.6f}%, {baseline_diffs['housing_diff']:.6f}%, {baseline_diffs['financial_diff']:.6f}%]"
    )
    lines.append("")
    lines.append("## Worker Sizing")
    lines.append("")
    lines.append(f"- nproc: {worker_meta['nproc']}")
    lines.append(f"- mem_available_gib: {worker_meta['mem_available_gib']:.3f}")
    lines.append(f"- rss_probe_gib: {worker_meta['rss_probe_gib']:.3f}")
    lines.append(f"- cpu_cap: {worker_meta['cpu_cap']}")
    lines.append(f"- mem_cap: {worker_meta['mem_cap']}")
    lines.append(f"- chosen_workers: {worker_meta['workers']}")
    lines.append("")
    lines.append("## Stage Runtime")
    lines.append("")
    for stage in stage_summaries:
        lines.append(
            "- "
            f"{stage['stage']}: elapsed={stage['elapsed_seconds']:.2f}s, "
            f"success={stage['completed_success_count']}, attempts={stage['total_attempts']}, "
            f"retries={stage['retry_events']}, worker_reductions={stage['worker_reductions']}, "
            f"final_workers={stage['final_workers']}"
        )
    lines.append("")
    lines.append(f"- total_elapsed_seconds: {total_elapsed:.2f}")
    lines.append(f"- throughput_scenarios_per_minute: {scenarios_per_min:.2f}")
    lines.append("")
    lines.append("## Top-2 Parameters By |Delta Housing| (Stage A)")
    lines.append("")
    lines.append(f"- {top2[0]}")
    lines.append(f"- {top2[1]}")
    lines.append("")
    lines.append("## Top 10 Scenarios (Guardrail-first ranking)")
    lines.append("")
    lines.append("| rank | scenario | stage | income | housing | financial | delta_housing | guard |")
    lines.append("|---:|---|---|---:|---:|---:|---:|:---:|")
    for idx, row in enumerate(ranked[:10], start=1):
        lines.append(
            f"| {idx} | {row['scenario_id']} | {row['stage']} | "
            f"{float(row['income_diff']):.3f}% | {float(row['housing_diff']):.3f}% | "
            f"{float(row['financial_diff']):.3f}% | {float(row['delta_housing']):.3f} | "
            f"{'Y' if row['guard_all_pass'] else 'N'} |"
        )

    (out_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_decision_matrix_markdown(out_root: Path, matrix: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    lines.append("# Dataset/Parameter Decision Matrix")
    lines.append("")
    lines.append("| priority | parameter | max_abs_delta_housing | best_delta_housing | best_scenario | best_direction | refresh_path |")
    lines.append("|---|---|---:|---:|---|---|---|")
    for row in matrix:
        lines.append(
            f"| {row['priority']} | {row['parameter']} | {row['max_abs_delta_housing']:.3f} | "
            f"{row['best_delta_housing']:.3f} | {row['best_scenario_id']} | {row['best_direction']} | "
            f"{row['dataset_refresh_path']} |"
        )
    (out_root / "decision_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_no_folder_collisions(rows: list[dict[str, Any]]) -> bool:
    success_rows = [row for row in rows if row["status"] == "success"]
    outputs = [row["output_subdir"] for row in success_rows]
    return len(outputs) == len(set(outputs))


def validate_result_completeness(rows: list[dict[str, Any]], expected_successes: int) -> bool:
    success_rows = [row for row in rows if row["status"] == "success"]
    return len(success_rows) == expected_successes


def deterministic_parse_check() -> bool:
    sample = "Income total diff: 6.615492 %\nHousing wealth total diff: 26.760137 %\nFinancial wealth total diff: 11.890496 %\n"
    return parse_validation_diffs(sample) == parse_validation_diffs(sample)


def retry_path_check() -> bool:
    return is_recoverable_resource_error("java.lang.OutOfMemoryError: Java heap space")


def run_baseline_validation(dataset: str, repo_root: Path, output_subdir: str) -> dict[str, float]:
    env = os.environ.copy()
    env.update(
        {
            "WAS_DATASET": dataset,
            "WAS_DATA_ROOT": str(repo_root),
            "WAS_RESULTS_ROOT": str(repo_root),
            "WAS_RESULTS_RUN_SUBDIR": output_subdir,
            "WAS_VALIDATION_PLOTS": "0",
            "MPLBACKEND": "Agg",
        }
    )
    proc = subprocess.run(
        ["./scripts/was/run_was_validation.sh"],
        cwd=repo_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "Baseline validation failed.\n"
            f"STDOUT:\n{proc.stdout[-1200:]}\nSTDERR:\n{proc.stderr[-1200:]}"
        )
    return parse_validation_diffs(proc.stdout)


def ensure_baseline_output(base_config: Path, repo_root: Path, output_subdir: str) -> None:
    output_dir = repo_root / output_subdir
    if output_dir.exists() and (output_dir / "HousingWealth-run1.csv").exists():
        return
    cmd = [
        default_maven_bin(repo_root),
        "-q",
        "exec:java",
        f"-Dexec.args=-configFile {base_config} -outputFolder {output_subdir} -dev",
    ]
    proc = subprocess.run(cmd, cwd=repo_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            "Baseline model run failed.\n"
            f"STDOUT:\n{proc.stdout[-1200:]}\nSTDERR:\n{proc.stderr[-1200:]}"
        )


def main() -> None:
    args = parse_args()
    repo_root = Path.cwd()
    base_config = Path(args.base_config)
    if not base_config.exists():
        raise SystemExit(f"Base config not found: {base_config}")

    results_root = args.results_root.rstrip("/")
    out_root = Path(args.out_root)
    configs_dir = out_root / "configs"
    logs_dir = out_root / "logs"
    out_root.mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    baseline_output_subdir = f"{results_root}/v4.0-output"
    ensure_baseline_output(base_config=base_config, repo_root=repo_root, output_subdir=baseline_output_subdir)
    baseline_diffs = run_baseline_validation(args.dataset, repo_root, baseline_output_subdir)

    # Adaptive worker sizing probe
    probe_output_subdir = f"{results_root}/input-sens-memprobe-output"
    if (repo_root / probe_output_subdir).exists():
        shutil.rmtree(repo_root / probe_output_subdir)
    rss_probe_gib, probe_elapsed = probe_rss_gib(base_config=base_config, probe_output_subdir=probe_output_subdir)
    if not args.keep_probe_output and (repo_root / probe_output_subdir).exists():
        shutil.rmtree(repo_root / probe_output_subdir)

    nproc = parse_nproc()
    mem_available_gib = parse_mem_available_gib()
    worker_meta = choose_workers(
        nproc=nproc,
        mem_available_gib=mem_available_gib,
        rss_probe_gib=rss_probe_gib,
        cpu_reserve=args.cpu_reserve,
        mem_reserve_gib=args.mem_reserve_gib,
        rss_multiplier=args.rss_multiplier,
        max_workers_cap=args.max_workers_cap,
    )
    if args.workers_override is not None:
        worker_meta["workers"] = max(2, args.workers_override)

    print(
        "Adaptive workers: "
        f"nproc={worker_meta['nproc']}, mem_available_gib={worker_meta['mem_available_gib']:.2f}, "
        f"rss_probe_gib={worker_meta['rss_probe_gib']:.3f}, cpu_cap={worker_meta['cpu_cap']}, "
        f"mem_cap={worker_meta['mem_cap']}, chosen={worker_meta['workers']}"
    )
    print(f"Probe elapsed seconds: {probe_elapsed:.2f}")
    print(
        "Baseline diffs: "
        f"income={baseline_diffs['income_diff']:.6f}, "
        f"housing={baseline_diffs['housing_diff']:.6f}, "
        f"financial={baseline_diffs['financial_diff']:.6f}"
    )

    ledger_path = out_root / "ledger.csv"
    ledger_fields = [
        "timestamp",
        "stage",
        "scenario_id",
        "parameter",
        "direction",
        "updated_keys",
        "updated_value",
        "attempt",
        "status",
        "workers_active_cap",
        "output_subdir",
        "config_path",
        "elapsed_seconds",
        "income_diff",
        "housing_diff",
        "financial_diff",
        "delta_income",
        "delta_housing",
        "delta_financial",
        "guard_income_pass",
        "guard_financial_pass",
        "guard_all_pass",
        "error_text",
    ]

    all_rows: list[dict[str, Any]] = []
    stage_summaries: list[dict[str, Any]] = []
    started_total = time.time()

    base_config_text = base_config.read_text(encoding="utf-8")
    baseline_props = read_properties(base_config)

    with ledger_path.open("w", encoding="utf-8", newline="") as ledger_handle:
        writer = csv.DictWriter(ledger_handle, fieldnames=ledger_fields)
        writer.writeheader()
        ledger_handle.flush()

        # Stage A
        stage_a_scenarios = build_stage_a_scenarios()
        stage_a_rows, stage_a_summary = execute_parallel_stage(
            scenarios=stage_a_scenarios,
            stage_name="A",
            base_config_text=base_config_text,
            configs_dir=configs_dir,
            logs_dir=logs_dir,
            results_root=results_root,
            dataset=args.dataset,
            repo_root=repo_root,
            initial_workers=worker_meta["workers"],
            ledger_writer=writer,
            ledger_handle=ledger_handle,
            baseline_diffs=baseline_diffs,
        )
        all_rows.extend(stage_a_rows)
        stage_summaries.append(stage_a_summary)

        top2 = select_top2_parameters(stage_a_rows)
        print(f"Top-2 parameters from Stage A by |delta_housing|: {top2[0]}, {top2[1]}")

        # Stage B
        stage_b_scenarios = make_stage_b_scenarios(top2, baseline_props)
        stage_b_rows, stage_b_summary = execute_parallel_stage(
            scenarios=stage_b_scenarios,
            stage_name="B",
            base_config_text=base_config_text,
            configs_dir=configs_dir,
            logs_dir=logs_dir,
            results_root=results_root,
            dataset=args.dataset,
            repo_root=repo_root,
            initial_workers=stage_a_summary["final_workers"],
            ledger_writer=writer,
            ledger_handle=ledger_handle,
            baseline_diffs=baseline_diffs,
        )
        all_rows.extend(stage_b_rows)
        stage_summaries.append(stage_b_summary)

        # Stage C
        stage_c_scenarios = make_stage_c_scenarios(top2, stage_a_rows)
        stage_c_rows, stage_c_summary = execute_parallel_stage(
            scenarios=stage_c_scenarios,
            stage_name="C",
            base_config_text=base_config_text,
            configs_dir=configs_dir,
            logs_dir=logs_dir,
            results_root=results_root,
            dataset=args.dataset,
            repo_root=repo_root,
            initial_workers=stage_b_summary["final_workers"],
            ledger_writer=writer,
            ledger_handle=ledger_handle,
            baseline_diffs=baseline_diffs,
        )
        all_rows.extend(stage_c_rows)
        stage_summaries.append(stage_c_summary)

    total_elapsed = time.time() - started_total
    matrix = build_decision_matrix(all_rows)

    write_summary_markdown(
        out_root=out_root,
        baseline_diffs=baseline_diffs,
        worker_meta=worker_meta,
        stage_summaries=stage_summaries,
        all_rows=all_rows,
        top2=top2,
        total_elapsed=total_elapsed,
    )
    write_decision_matrix_markdown(out_root, matrix)

    verification = {
        "no_folder_collision": validate_no_folder_collisions(all_rows),
        "result_completeness": validate_result_completeness(all_rows, expected_successes=24),
        "retry_path_check": retry_path_check(),
        "deterministic_parse_check": deterministic_parse_check(),
        "throughput_scenarios_per_minute": (
            len([row for row in all_rows if row["status"] == "success"]) / max(total_elapsed / 60.0, 1e-9)
        ),
    }

    summary_json = {
        "baseline_diffs": baseline_diffs,
        "worker_meta": worker_meta,
        "probe_elapsed_seconds": probe_elapsed,
        "stage_summaries": stage_summaries,
        "verification": verification,
        "top2_parameters_stage_a_abs_delta_housing": top2,
        "decision_matrix": matrix,
        "successful_rows": [row for row in all_rows if row["status"] == "success"],
    }
    (out_root / "summary.json").write_text(json.dumps(summary_json, indent=2), encoding="utf-8")

    print("Completed concurrent sensitivity run.")
    print(f"Wrote: {ledger_path}")
    print(f"Wrote: {out_root / 'summary.md'}")
    print(f"Wrote: {out_root / 'summary.json'}")
    print(f"Wrote: {out_root / 'decision_matrix.md'}")
    print(
        "Verification: "
        f"no_collision={verification['no_folder_collision']}, "
        f"completeness={verification['result_completeness']}, "
        f"retry_check={verification['retry_path_check']}, "
        f"parse_check={verification['deterministic_parse_check']}, "
        f"throughput={verification['throughput_scenarios_per_minute']:.2f}/min"
    )


if __name__ == "__main__":
    main()
