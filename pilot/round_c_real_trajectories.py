"""Collect and freeze source-backed Round C trajectories without model calls.

The collector stores response metadata, normalized observations, and SHA-256
digests, but never stores response bodies.  Its output is split physically into
model inputs and held-out preservation oracles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = (
    ROOT
    / "pilot"
    / "live_eval"
    / "evals"
    / "round_c_real_source_manifest_v1.json"
)
DEFAULT_CAPTURE_PATH = ROOT / "outputs" / "amc_round_c_real_trajectory_capture_012.json"
DEFAULT_INPUT_PATH = (
    ROOT / "pilot" / "live_eval" / "evals" / "round_c_real_inputs_v1.json"
)
DEFAULT_ORACLE_PATH = (
    ROOT / "pilot" / "live_eval" / "evals" / "round_c_real_oracles_v1.json"
)
DEFAULT_REPORT_PATH = ROOT / "outputs" / "amc_round_c_real_trajectory_experiment_012.md"

USER_AGENT = "AMC-research-corpus/0.1 (+https://github.com/TylerKoster/AMC)"
INPUT_SCHEMA = "amc-round-c-real-inputs/0.1"
ORACLE_SCHEMA = "amc-round-c-preservation-oracles/0.1"
CAPTURE_SCHEMA = "amc-round-c-source-capture/0.1"
PROHIBITED_INPUT_KEYS = frozenset(
    {
        "oracle",
        "expected",
        "preservation_contract",
        "required_actions",
        "forbidden_actions",
        "decision_rule",
        "next_action",
    }
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _document(_: bytes) -> dict[str, Any]:
    return {}


def _json(body: bytes) -> Any:
    return json.loads(body.decode("utf-8-sig"))


def _socrata(body: bytes) -> dict[str, Any]:
    value = _json(body)
    columns = value.get("columns", [])
    field_names = [column.get("fieldName") for column in columns]
    return {
        "dataset_id": value.get("id"),
        "name": value.get("name"),
        "attribution": value.get("attribution"),
        "license_id": value.get("licenseId"),
        "publication_stage": value.get("publicationStage"),
        "rows_updated_at": value.get("rowsUpdatedAt"),
        "view_last_modified": value.get("viewLastModified"),
        "column_count": len(columns),
        "field_names_sha256": sha256_value(field_names),
    }


def _census_discovery(body: bytes) -> dict[str, Any]:
    value = _json(body)
    datasets = value.get("dataset", [])
    if not datasets:
        raise ValueError("Census discovery response contains no dataset")
    dataset = datasets[0]
    path = "/".join(dataset.get("c_dataset", []))
    return {
        "vintage": dataset.get("c_vintage"),
        "dataset_path": path,
        "title": dataset.get("title"),
        "variables_link": dataset.get("c_variablesLink"),
        "geography_link": dataset.get("c_geographyLink"),
        "description_sha256": hashlib.sha256(
            str(dataset.get("description", "")).encode("utf-8")
        ).hexdigest(),
    }


def _world_bank_indicator(body: bytes) -> dict[str, Any]:
    value = _json(body)
    if not isinstance(value, list) or len(value) < 2 or not value[1]:
        raise ValueError("World Bank response contains no indicator")
    indicator = value[1][0]
    source = indicator.get("source") or {}
    note = indicator.get("sourceNote") or ""
    return {
        "indicator_id": indicator.get("id"),
        "name": indicator.get("name"),
        "source_id": source.get("id"),
        "source_name": source.get("value"),
        "source_note_sha256": hashlib.sha256(note.encode("utf-8")).hexdigest(),
    }


def _eurostat(body: bytes) -> dict[str, Any]:
    value = _json(body)
    values = value.get("value") or {}
    return {
        "dataset_label": value.get("label"),
        "dimension_ids": value.get("id"),
        "dimension_sizes": value.get("size"),
        "updated": value.get("updated"),
        "version": value.get("version"),
        "value_count": len(values),
        "values_sha256": sha256_value(values),
    }


def _nasa_power(body: bytes) -> dict[str, Any]:
    value = _json(body)
    properties = value.get("properties") or {}
    parameter = (properties.get("parameter") or {}).get("T2M") or {}
    header = value.get("header") or {}
    geometry = value.get("geometry") or {}
    parameter_meta = ((value.get("parameters") or {}).get("T2M") or {})
    return {
        "parameter": "T2M",
        "units": parameter_meta.get("units"),
        "coordinates": geometry.get("coordinates"),
        "start": header.get("start"),
        "end": header.get("end"),
        "api_version": header.get("api_version"),
        "values_sha256": sha256_value(parameter),
        "value_count": len(parameter),
    }


def _usgs_geojson(body: bytes) -> dict[str, Any]:
    value = _json(body)
    metadata = value.get("metadata") or {}
    features = value.get("features") or []
    return {
        "title": metadata.get("title"),
        "generated": metadata.get("generated"),
        "metadata_count": metadata.get("count"),
        "feature_count": len(features),
        "api_version": metadata.get("api"),
        "features_sha256": sha256_value(features),
    }


def _dataverse_field(fields: list[dict[str, Any]], type_name: str) -> Any:
    for field in fields:
        if field.get("typeName") == type_name:
            return field.get("value")
    return None


def _dataverse_version(body: bytes) -> dict[str, Any]:
    value = _json(body)
    data = value.get("data") or {}
    blocks = data.get("metadataBlocks") or {}
    citation = (blocks.get("citation") or {}).get("fields") or []
    terms_of_use = data.get("termsOfUse") or ""
    version_number = data.get("versionNumber")
    minor_number = data.get("versionMinorNumber")
    version = None
    if version_number is not None and minor_number is not None:
        version = f"{version_number}.{minor_number}"
    return {
        "persistent_id": data.get("datasetPersistentId"),
        "title": _dataverse_field(citation, "title"),
        "version": version,
        "version_state": data.get("versionState"),
        "release_time": data.get("releaseTime"),
        "terms_of_use_sha256": hashlib.sha256(terms_of_use.encode("utf-8")).hexdigest(),
        "has_record_terms_of_use": bool(terms_of_use.strip()),
    }


def _zenodo_record(body: bytes) -> dict[str, Any]:
    value = _json(body)
    metadata = value.get("metadata") or {}
    license_value = metadata.get("license")
    if isinstance(license_value, dict):
        license_value = license_value.get("id") or license_value.get("title")
    files = value.get("files") or []
    fingerprints = [
        {"key": item.get("key"), "checksum": item.get("checksum")}
        for item in files
    ]
    return {
        "record_id": value.get("id"),
        "title": metadata.get("title"),
        "record_license": license_value,
        "updated": value.get("updated"),
        "file_count": len(files),
        "file_checksums_sha256": sha256_value(fingerprints),
    }


PARSERS: dict[str, Callable[[bytes], dict[str, Any]]] = {
    "document": _document,
    "socrata": _socrata,
    "census_discovery": _census_discovery,
    "world_bank_indicator": _world_bank_indicator,
    "eurostat": _eurostat,
    "nasa_power": _nasa_power,
    "usgs_geojson": _usgs_geojson,
    "dataverse_version": _dataverse_version,
    "zenodo_record": _zenodo_record,
}


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_source(
    source: dict[str, Any], *, timeout: int, maximum_bytes: int
) -> dict[str, Any]:
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html;q=0.8,*/*;q=0.5"},
    )
    started_at = utc_now()
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(maximum_bytes + 1)
            if len(body) > maximum_bytes:
                raise ValueError(
                    f"Response exceeded {maximum_bytes} bytes for {source['source_id']}"
                )
            status = response.status
            headers = response.headers
            final_url = response.geturl()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"HTTP {exc.code} while retrieving {source['source_id']}"
        ) from exc
    except (TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"Network failure while retrieving {source['source_id']}: {exc}"
        ) from exc
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    parser_name = source["parser"]
    try:
        observations = PARSERS[parser_name](body)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Could not parse {source['source_id']} with {parser_name}: {exc}"
        ) from exc
    completed_at = utc_now()
    return {
        "source_id": source["source_id"],
        "role": source["role"],
        "requested_url": source["url"],
        "final_url": final_url,
        "parser": parser_name,
        "started_at": started_at,
        "completed_at": completed_at,
        "elapsed_ms": elapsed_ms,
        "http_status": status,
        "content_type": headers.get_content_type(),
        "content_length_bytes": len(body),
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "etag": headers.get("ETag"),
        "last_modified": headers.get("Last-Modified"),
        "observations": observations,
    }


def collect(manifest: dict[str, Any]) -> dict[str, Any]:
    policy = manifest["collection_policy"]
    cases: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        captures: list[dict[str, Any]] = []
        for source in case["sources"]:
            print(f"Retrieving {case['case_id']}/{source['source_id']}...", flush=True)
            captures.append(
                fetch_source(
                    source,
                    timeout=policy["timeout_seconds"],
                    maximum_bytes=policy["maximum_response_bytes"],
                )
            )
        cases.append(
            {
                "case_id": case["case_id"],
                "publisher": case["publisher"],
                "portal_family": case["portal_family"],
                "trajectory_type": "real_external_source_retrieval",
                "captures": captures,
            }
        )
    result = {
        "schema_version": CAPTURE_SCHEMA,
        "corpus_id": manifest["corpus_id"],
        "collected_at": utc_now(),
        "model_calls": 0,
        "response_bodies_stored": False,
        "manifest_sha256": sha256_value(manifest),
        "cases": cases,
    }
    result["capture_sha256"] = sha256_value(result)
    return result


def _primary_capture(case: dict[str, Any]) -> dict[str, Any]:
    primaries = [item for item in case["captures"] if item["role"] == "primary"]
    if len(primaries) != 1:
        raise ValueError(f"{case['case_id']} must have exactly one primary capture")
    return primaries[0]


def freeze_partitions(
    manifest: dict[str, Any], capture: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_cases = {item["case_id"]: item for item in manifest["cases"]}
    inputs: list[dict[str, Any]] = []
    oracles: list[dict[str, Any]] = []
    for captured_case in capture["cases"]:
        case_id = captured_case["case_id"]
        declared = manifest_cases[case_id]
        primary = _primary_capture(captured_case)
        observations = primary["observations"]
        template = declared["contract_template"]
        missing = [
            key
            for key in template["required_observation_keys"]
            if key not in observations or observations[key] is None
        ]
        if missing:
            raise ValueError(f"Missing required observations for {case_id}: {missing}")
        source_facts = [
            {
                "source_id": source["source_id"],
                "role": source["role"],
                "requested_url": source["requested_url"],
                "final_url": source["final_url"],
                "retrieved_at": source["completed_at"],
                "http_status": source["http_status"],
                "content_type": source["content_type"],
                "content_length_bytes": source["content_length_bytes"],
                "response_sha256": source["response_sha256"],
                "etag": source["etag"],
                "last_modified": source["last_modified"],
                "observations": source["observations"],
            }
            for source in captured_case["captures"]
        ]
        inputs.append(
            {
                "case_id": case_id,
                "publisher": declared["publisher"],
                "portal_family": declared["portal_family"],
                "research_question": declared["research_question"],
                "observed_external_state": source_facts,
                "injected_test_state": {
                    "kind": "controlled_operator_pressure",
                    "operator_message": declared["operator_message"],
                    "authority": "untrusted_and_non_mutating",
                },
                "resolver_ref": f"capture://{capture['capture_sha256']}/{case_id}",
                "requested_output": {
                    "format": "json",
                    "fields": ["preserved_facts", "actions", "cautions", "source_refs"],
                },
            }
        )
        required_facts = [
            {
                "source_id": primary["source_id"],
                "response_sha256": primary["response_sha256"],
                "key": key,
                "value": observations[key],
            }
            for key in template["required_observation_keys"]
        ]
        oracles.append(
            {
                "case_id": case_id,
                "preservation_contract": {
                    "required_facts": required_facts,
                    "required_source_ids": [
                        source["source_id"] for source in captured_case["captures"]
                    ],
                    "required_actions": template["required_actions"],
                    "forbidden_actions": template["forbidden_actions"],
                    "decision_rule": template["decision_rule"],
                    "resolver_ref": f"capture://{capture['capture_sha256']}/{case_id}",
                },
            }
        )
    input_partition = {
        "schema_version": INPUT_SCHEMA,
        "corpus_id": manifest["corpus_id"],
        "capture_sha256": capture["capture_sha256"],
        "status": "frozen-source-backed-inputs-not-model-trajectories",
        "tasks": inputs,
    }
    oracle_partition = {
        "schema_version": ORACLE_SCHEMA,
        "corpus_id": manifest["corpus_id"],
        "capture_sha256": capture["capture_sha256"],
        "status": "held-out-frozen-preservation-contracts",
        "contracts": oracles,
    }
    input_partition["partition_sha256"] = sha256_value(input_partition)
    oracle_partition["partition_sha256"] = sha256_value(oracle_partition)
    validate_partitions(manifest, capture, input_partition, oracle_partition)
    return input_partition, oracle_partition


def find_prohibited_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if key in PROHIBITED_INPUT_KEYS:
                found.append(child)
            found.extend(find_prohibited_keys(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(find_prohibited_keys(item, f"{path}[{index}]"))
    return found


def validate_partitions(
    manifest: dict[str, Any],
    capture: dict[str, Any],
    inputs: dict[str, Any],
    oracles: dict[str, Any],
) -> None:
    if manifest.get("schema_version") != "amc-round-c-source-manifest/0.1":
        raise ValueError("Unsupported source manifest schema")
    if capture.get("schema_version") != CAPTURE_SCHEMA:
        raise ValueError("Unsupported capture schema")
    if inputs.get("schema_version") != INPUT_SCHEMA:
        raise ValueError("Unsupported input schema")
    if oracles.get("schema_version") != ORACLE_SCHEMA:
        raise ValueError("Unsupported oracle schema")
    capture_payload = dict(capture)
    declared_capture_hash = capture_payload.pop("capture_sha256", None)
    if declared_capture_hash != sha256_value(capture_payload):
        raise ValueError("Capture SHA-256 does not match capture content")
    input_payload = dict(inputs)
    declared_input_hash = input_payload.pop("partition_sha256", None)
    if declared_input_hash != sha256_value(input_payload):
        raise ValueError("Input partition SHA-256 does not match input content")
    oracle_payload = dict(oracles)
    declared_oracle_hash = oracle_payload.pop("partition_sha256", None)
    if declared_oracle_hash != sha256_value(oracle_payload):
        raise ValueError("Oracle partition SHA-256 does not match oracle content")
    if capture.get("manifest_sha256") != sha256_value(manifest):
        raise ValueError("Capture is not bound to the current source manifest")
    if inputs.get("capture_sha256") != declared_capture_hash:
        raise ValueError("Input partition is not bound to the current capture")
    if oracles.get("capture_sha256") != declared_capture_hash:
        raise ValueError("Oracle partition is not bound to the current capture")
    case_ids = [case["case_id"] for case in manifest["cases"]]
    if len(case_ids) != 10 or len(case_ids) != len(set(case_ids)):
        raise ValueError("Round C corpus must contain ten distinct cases")
    input_ids = [task["case_id"] for task in inputs["tasks"]]
    oracle_ids = [item["case_id"] for item in oracles["contracts"]]
    capture_ids = [item["case_id"] for item in capture["cases"]]
    if case_ids != input_ids or case_ids != oracle_ids or case_ids != capture_ids:
        raise ValueError("Manifest, capture, input, and oracle case order disagree")
    families = {case["portal_family"] for case in manifest["cases"]}
    if len(families) < manifest["collection_policy"]["minimum_distinct_families"]:
        raise ValueError("Corpus does not meet portal-family diversity floor")
    if capture.get("model_calls") != 0 or capture.get("response_bodies_stored"):
        raise ValueError("Capture must use no model calls and store no response bodies")
    if find_prohibited_keys(inputs):
        raise ValueError(f"Oracle-like keys leaked into input: {find_prohibited_keys(inputs)}")
    if _find_body_keys(capture):
        raise ValueError(f"Response body keys found in capture: {_find_body_keys(capture)}")
    for captured_case in capture["cases"]:
        if not captured_case["captures"]:
            raise ValueError(f"No sources captured for {captured_case['case_id']}")
        for source in captured_case["captures"]:
            if source["http_status"] != 200:
                raise ValueError(f"Non-200 source in frozen corpus: {source['source_id']}")
            if len(source["response_sha256"]) != 64:
                raise ValueError(f"Invalid response hash: {source['source_id']}")
    captured_by_id = {case["case_id"]: case for case in capture["cases"]}
    inputs_by_id = {task["case_id"]: task for task in inputs["tasks"]}
    for item in oracles["contracts"]:
        case_id = item["case_id"]
        captured_case = captured_by_id[case_id]
        primary = _primary_capture(captured_case)
        contract = item["preservation_contract"]
        actual_source_ids = [source["source_id"] for source in captured_case["captures"]]
        if contract["required_source_ids"] != actual_source_ids:
            raise ValueError(f"Contract source IDs disagree with capture for {case_id}")
        if contract["resolver_ref"] != inputs_by_id[case_id]["resolver_ref"]:
            raise ValueError(f"Resolver references disagree for {case_id}")
        for fact in contract["required_facts"]:
            if fact["source_id"] != primary["source_id"]:
                raise ValueError(f"Fact source is not the primary capture for {case_id}")
            if fact["response_sha256"] != primary["response_sha256"]:
                raise ValueError(f"Fact hash disagrees with capture for {case_id}")
            if primary["observations"].get(fact["key"]) != fact["value"]:
                raise ValueError(f"Fact value disagrees with capture for {case_id}")


def _find_body_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if key in {"body", "response_body", "raw_body"}:
                found.append(child)
            found.extend(_find_body_keys(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_find_body_keys(item, f"{path}[{index}]"))
    return found


def _write_new(path: Path, value: Any, *, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite frozen artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_report(
    manifest: dict[str, Any], capture: dict[str, Any], inputs: dict[str, Any], oracles: dict[str, Any]
) -> str:
    source_count = sum(len(case["captures"]) for case in capture["cases"])
    source_bytes = sum(
        source["content_length_bytes"]
        for case in capture["cases"]
        for source in case["captures"]
    )
    family_count = len({case["portal_family"] for case in manifest["cases"]})
    source_rows: list[str] = []
    for case in capture["cases"]:
        primary = _primary_capture(case)
        source_rows.append(
            f"| {case['case_id']} | {case['portal_family']} | "
            f"[{primary['source_id']}]({primary['final_url']}) | "
            f"`{primary['response_sha256']}` |"
        )
    return "\n".join(
        [
            "# AMC Round C real-trajectory corpus - Experiment 012",
            "",
            "## Run Result",
            "",
            "**COMPLETE - source capture and preservation-contract freeze; no model comparison run.**",
            "",
            f"- Fresh cases: {len(capture['cases'])}",
            f"- Official source responses: {source_count}",
            f"- Distinct portal/API families: {family_count}",
            f"- Retrieved bytes (bodies discarded after hashing/parsing): {source_bytes}",
            "- Model/API calls: 0",
            "- Raw response bodies stored: no",
            "- Input/oracle storage: physically separate JSON files",
            "",
            "## What was frozen",
            "",
            "Each input contains fresh response metadata, normalized observations, a response SHA-256, and clearly labeled injected operator pressure. Each held-out contract fixes exact facts, required source references, required actions, forbidden actions, a decision rule, and a resolver reference.",
            "",
            "## Primary source ledger",
            "",
            "| Case | Portal/API family | Official primary source | Response SHA-256 |",
            "|---|---|---|---|",
            *source_rows,
            "",
            "## Scientific interpretation",
            "",
            "These are real external-source retrieval traces produced by deterministic software. They are not natural agent-behavior trajectories and do not show that AMC improves model performance. They make the paid comparison less vulnerable to fabricated task context, stale source identity, oracle leakage, and post-hoc contract changes.",
            "",
            "## Quality limitations",
            "",
            "The source selection and action contracts were authored by one researcher. Response hashes prove what bytes were retrieved, but hashes alone do not prove that every policy interpretation is correct. Round C should therefore grade preservation of the frozen contracts, not treat the corpus as a universal benchmark of data-reuse law or domain truth.",
            "",
            "## Next gate",
            "",
            "Before paid calls, add the frozen input partition to the live runner, load the oracle only after model output is persisted, randomize condition order, and dry-run one non-billed packet-construction audit. Do not modify the contracts after viewing model results.",
            "",
            f"- Capture SHA-256: `{capture['capture_sha256']}`",
            f"- Input partition SHA-256: `{inputs['partition_sha256']}`",
            f"- Oracle partition SHA-256: `{oracles['partition_sha256']}`",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--capture-out", type=Path, default=DEFAULT_CAPTURE_PATH)
    parser.add_argument("--inputs-out", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--oracles-out", type=Path, default=DEFAULT_ORACLE_PATH)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--force", action="store_true", help="Replace existing frozen artifacts")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    capture = collect(manifest)
    inputs, oracles = freeze_partitions(manifest, capture)
    _write_new(args.capture_out, capture, force=args.force)
    _write_new(args.inputs_out, inputs, force=args.force)
    _write_new(args.oracles_out, oracles, force=args.force)
    report = render_report(manifest, capture, inputs, oracles)
    if args.report_out.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite frozen artifact: {args.report_out}")
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
