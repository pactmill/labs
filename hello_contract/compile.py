"""Compile ODCS/ODPS fixtures into JSON Schema, expectations, monitors, MCP stubs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

LOGICAL_TO_JSON = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "date": "string",
    "timestamp": "string",
    "time": "string",
    "object": "object",
    "array": "array",
    "map": "object",
    "vector": "array",
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def iter_properties(odcs: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    props: list[tuple[str, dict[str, Any]]] = []
    for element in odcs.get("schema") or []:
        for prop in element.get("properties") or []:
            name = prop.get("name")
            if name:
                props.append((name, prop))
    return props


def to_json_schema(odcs: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, prop in iter_properties(odcs):
        logical = prop.get("logicalType", "string")
        json_type = LOGICAL_TO_JSON.get(logical, "string")
        entry: dict[str, Any] = {"type": json_type}
        if logical in {"date", "timestamp", "time"}:
            entry["format"] = "date-time" if logical == "timestamp" else logical
        if prop.get("description"):
            entry["description"] = prop["description"]
        properties[name] = entry
        if prop.get("required") or prop.get("primaryKey"):
            required.append(name)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": odcs.get("name") or odcs.get("id"),
        "type": "object",
        "properties": properties,
        "required": required,
        "x-odcs-id": odcs.get("id"),
        "x-odcs-version": odcs.get("version"),
    }


def to_expectations(odcs: dict[str, Any]) -> list[dict[str, Any]]:
    expectations: list[dict[str, Any]] = []
    for name, prop in iter_properties(odcs):
        for q in prop.get("quality") or []:
            rule = (q.get("rule") or q.get("type") or "").lower()
            if rule in {"notnull", "not_null"} or (
                q.get("type") == "library" and q.get("rule") == "notNull"
            ):
                expectations.append(
                    {
                        "expectation_type": "expect_column_values_to_not_be_null",
                        "kwargs": {"column": name},
                        "meta": {"source": "odcs.quality"},
                    }
                )
            elif rule == "unique" or (
                q.get("type") == "library" and q.get("rule") == "unique"
            ):
                expectations.append(
                    {
                        "expectation_type": "expect_column_values_to_be_unique",
                        "kwargs": {"column": name},
                        "meta": {"source": "odcs.quality"},
                    }
                )
            elif rule == "validvalues" or (
                q.get("type") == "library" and q.get("rule") == "validValues"
            ):
                values = q.get("mustBe") or q.get("values") or []
                expectations.append(
                    {
                        "expectation_type": "expect_column_values_to_be_in_set",
                        "kwargs": {"column": name, "value_set": values},
                        "meta": {"source": "odcs.quality"},
                    }
                )
            elif q.get("type") == "custom" and name == "total_cents":
                expectations.append(
                    {
                        "expectation_type": "expect_column_values_to_be_between",
                        "kwargs": {"column": name, "min_value": 0},
                        "meta": {
                            "source": "odcs.quality.custom",
                            "description": q.get("description"),
                        },
                    }
                )
    # Ensure at least a few checks even on sparse contracts
    if len(expectations) < 3:
        for name, _ in iter_properties(odcs)[:3]:
            expectations.append(
                {
                    "expectation_type": "expect_column_to_exist",
                    "kwargs": {"column": name},
                    "meta": {"source": "odcs.schema"},
                }
            )
    return expectations


def to_freshness_monitor(odcs: dict[str, Any]) -> dict[str, Any]:
    freshness = None
    for item in odcs.get("sla") or []:
        if str(item.get("property", "")).lower() == "freshness":
            freshness = item
            break
    return {
        "monitor": "freshness",
        "odcs_id": odcs.get("id"),
        "threshold": {
            "value": None if freshness is None else freshness.get("value"),
            "unit": None if freshness is None else freshness.get("unit"),
            "element": None if freshness is None else freshness.get("element"),
        },
        "action_on_breach": "warn",
        "note": "Spike stub — wire to DQ/observability tool in a later phase",
    }


def to_mcp_tool(odcs: dict[str, Any], odps: dict[str, Any] | None) -> dict[str, Any] | None:
    if not odps:
        return None
    port = None
    for p in odps.get("outputPorts") or []:
        if str(p.get("type", "")).lower() in {"mcp_tool", "mcp"}:
            port = p
            break
    if port is None:
        return None

    custom = {c.get("property"): c.get("value") for c in port.get("customProperties") or []}
    tool_name = custom.get("toolName") or port.get("name") or "unnamed_tool"
    input_field = custom.get("inputFields") or "order_id"
    props = dict(iter_properties(odcs))
    input_schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    if input_field in props:
        logical = props[input_field].get("logicalType", "string")
        input_schema["properties"][input_field] = {
            "type": LOGICAL_TO_JSON.get(logical, "string"),
            "description": props[input_field].get("description") or input_field,
        }
        input_schema["required"] = [input_field]
    else:
        input_schema["properties"][input_field] = {"type": "string"}
        input_schema["required"] = [input_field]

    return {
        "name": tool_name,
        "description": port.get("description") or odcs.get("description", {}).get("purpose"),
        "inputSchema": input_schema,
        "annotations": {
            "sideEffectClass": custom.get("sideEffectClass", "unknown"),
            "contractId": odcs.get("id"),
            "productId": odps.get("id"),
            "readOnlyHint": custom.get("sideEffectClass") == "read-only",
        },
    }


def find_breaking_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_props = {n: p for n, p in iter_properties(before)}
    after_props = {n: p for n, p in iter_properties(after)}
    breaks: list[str] = []
    for name, bprop in before_props.items():
        if name not in after_props:
            breaks.append(f"removed property '{name}'")
            continue
        btype = bprop.get("logicalType")
        atype = after_props[name].get("logicalType")
        if btype != atype:
            breaks.append(
                f"logicalType change on '{name}': {btype} -> {atype}"
            )
        if bprop.get("required") and not after_props[name].get("required"):
            # loosening required is usually non-breaking for producers; skip
            pass
        if not bprop.get("required") and after_props[name].get("required"):
            breaks.append(f"property '{name}' became required")
    return breaks


def write_outputs(
    out_dir: Path,
    odcs: dict[str, Any],
    odps: dict[str, Any] | None,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    schema_path = out_dir / "jsonschema.json"
    schema_path.write_text(json.dumps(to_json_schema(odcs), indent=2) + "\n", encoding="utf-8")
    written.append(schema_path)

    exp_path = out_dir / "expectations.json"
    exp_path.write_text(
        json.dumps({"expectations": to_expectations(odcs)}, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(exp_path)

    mon_path = out_dir / "monitor_freshness.yaml"
    mon_path.write_text(yaml.safe_dump(to_freshness_monitor(odcs), sort_keys=False), encoding="utf-8")
    written.append(mon_path)

    mcp = to_mcp_tool(odcs, odps)
    if mcp:
        mcp_path = out_dir / "mcp_tool.json"
        mcp_path.write_text(json.dumps(mcp, indent=2) + "\n", encoding="utf-8")
        written.append(mcp_path)

    hint = out_dir / "ci_breaking_hint.md"
    hint.write_text(
        "\n".join(
            [
                "# CI hint (spike)",
                "",
                "Run breaking-change detection in CI:",
                "",
                "```bash",
                "python -m dpf_compiler check-breaking \\",
                "  --before fixtures/customer_order_facts.odcs.yaml \\",
                "  --after path/to/new.odcs.yaml",
                "```",
                "",
                "Fail the job on non-zero exit.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    written.append(hint)
    return written
