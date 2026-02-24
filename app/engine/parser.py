"""
Workflow YAML parser and validator.

Loads a YAML string and validates it against the workflow schema,
returning a typed WorkflowDefinition dict (plain Python dicts for flexibility).
"""

from __future__ import annotations

from typing import Any

import yaml

VALID_STEP_TYPES = {
    # Transforms
    "trim", "crop", "speed_change", "freeze_frame", "extract_frame",
    # Overlays
    "add_text", "add_image", "add_audio", "particles",
    # Effects
    "shake", "rotate", "color_grade", "transition",
    # Control flow
    "group", "conditional", "loop", "noop",
    # AI / external
    "agent_decision", "external_api",
}

VALID_ANALYSIS_TYPES = {
    "metadata", "scene_detection", "beat_detection",
    "transcription", "speaker_diarization", "silence_detection", "face_detection",
}

VALID_PARAMETER_TYPES = {"string", "integer", "float", "boolean", "timestamp", "file"}


class WorkflowParseError(ValueError):
    pass


def parse_workflow(yaml_content: str) -> dict[str, Any]:
    """Parse and validate a workflow YAML string.

    Returns the parsed workflow dict with normalized structure.
    Raises WorkflowParseError on validation failure.
    """
    try:
        doc = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise WorkflowParseError(f"Invalid YAML: {e}") from e

    if not isinstance(doc, dict):
        raise WorkflowParseError("Workflow must be a YAML mapping")

    _require_key(doc, "metadata", "mapping")
    _require_key(doc, "steps", "sequence")

    metadata = doc["metadata"]
    _require_key(metadata, "name", "string", parent="metadata")
    _require_key(metadata, "description", "string", parent="metadata")
    _require_key(metadata, "author", "string", parent="metadata")

    params = doc.get("parameters", [])
    if not isinstance(params, list):
        raise WorkflowParseError("'parameters' must be a list")
    for p in params:
        _validate_parameter(p)

    requires = doc.get("requires_analysis", [])
    if not isinstance(requires, list):
        raise WorkflowParseError("'requires_analysis' must be a list")
    for r in requires:
        if r not in VALID_ANALYSIS_TYPES:
            raise WorkflowParseError(f"Unknown analysis type: '{r}'")

    steps = doc["steps"]
    if not isinstance(steps, list):
        raise WorkflowParseError("'steps' must be a list")
    _validate_steps(steps)

    return doc


def _require_key(mapping: dict, key: str, kind: str, parent: str = "workflow") -> None:
    if key not in mapping:
        raise WorkflowParseError(f"'{parent}' is missing required key '{key}'")
    value = mapping[key]
    if kind == "string" and not isinstance(value, str):
        raise WorkflowParseError(f"'{parent}.{key}' must be a string, got {type(value).__name__}")
    if kind == "sequence" and not isinstance(value, list):
        raise WorkflowParseError(f"'{parent}.{key}' must be a list")
    if kind == "mapping" and not isinstance(value, dict):
        raise WorkflowParseError(f"'{parent}.{key}' must be a mapping")


def _validate_parameter(param: Any) -> None:
    if not isinstance(param, dict):
        raise WorkflowParseError("Each parameter must be a mapping")
    if "name" not in param:
        raise WorkflowParseError("Parameter missing 'name'")
    ptype = param.get("type", "string")
    if ptype not in VALID_PARAMETER_TYPES:
        raise WorkflowParseError(
            f"Parameter '{param['name']}' has unknown type '{ptype}'. "
            f"Valid types: {sorted(VALID_PARAMETER_TYPES)}"
        )


def _validate_steps(steps: list, parent_id: str = "root") -> None:
    ids_seen: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            raise WorkflowParseError(f"Each step in '{parent_id}' must be a mapping")
        if "id" not in step:
            raise WorkflowParseError(f"Step in '{parent_id}' is missing 'id'")
        if "type" not in step:
            raise WorkflowParseError(f"Step '{step['id']}' is missing 'type'")

        sid = step["id"]
        stype = step["type"]

        if sid in ids_seen:
            raise WorkflowParseError(f"Duplicate step id '{sid}' in '{parent_id}'")
        ids_seen.add(sid)

        if stype not in VALID_STEP_TYPES:
            raise WorkflowParseError(
                f"Step '{sid}' has unknown type '{stype}'. Valid: {sorted(VALID_STEP_TYPES)}"
            )

        # Recurse into nested steps
        if stype == "group" and "steps" in step:
            _validate_steps(step["steps"], parent_id=sid)
        if stype == "conditional":
            if "then" in step and isinstance(step["then"], list):
                _validate_steps(step["then"], parent_id=f"{sid}.then")
            if "else" in step and isinstance(step["else"], list):
                _validate_steps(step["else"], parent_id=f"{sid}.else")
        if stype == "loop" and "steps" in step:
            _validate_steps(step["steps"], parent_id=sid)


def build_param_defaults(workflow_def: dict[str, Any]) -> dict[str, Any]:
    """Return a dict of parameter name → default value."""
    defaults: dict[str, Any] = {}
    for param in workflow_def.get("parameters", []):
        if "default" in param:
            defaults[param["name"]] = param["default"]
    return defaults


def validate_params(workflow_def: dict[str, Any], provided: dict[str, Any]) -> dict[str, Any]:
    """
    Merge provided params with defaults and validate required/type constraints.

    Returns the final resolved params dict.
    Raises WorkflowParseError on missing required params or type mismatches.
    """
    defaults = build_param_defaults(workflow_def)
    result = {**defaults, **provided}

    for param in workflow_def.get("parameters", []):
        name = param["name"]
        required = param.get("required", False)

        if name not in result:
            if required:
                raise WorkflowParseError(f"Required parameter '{name}' was not provided")
            continue

        value = result[name]
        ptype = param.get("type", "string")

        # Type coercion / validation
        if ptype == "integer":
            try:
                result[name] = int(value)
            except (TypeError, ValueError):
                raise WorkflowParseError(f"Parameter '{name}' must be an integer")
            v = result[name]
            if "min" in param and v < param["min"]:
                raise WorkflowParseError(f"Parameter '{name}' must be >= {param['min']}")
            if "max" in param and v > param["max"]:
                raise WorkflowParseError(f"Parameter '{name}' must be <= {param['max']}")
        elif ptype == "float":
            try:
                result[name] = float(value)
            except (TypeError, ValueError):
                raise WorkflowParseError(f"Parameter '{name}' must be a float")
            v = result[name]
            if "min" in param and v < param["min"]:
                raise WorkflowParseError(f"Parameter '{name}' must be >= {param['min']}")
            if "max" in param and v > param["max"]:
                raise WorkflowParseError(f"Parameter '{name}' must be <= {param['max']}")
        elif ptype == "boolean":
            if isinstance(value, str):
                result[name] = value.lower() in ("true", "1", "yes")
            else:
                result[name] = bool(value)
        elif ptype == "string":
            if "enum" in param and value not in param["enum"]:
                raise WorkflowParseError(
                    f"Parameter '{name}' must be one of {param['enum']}, got '{value}'"
                )

    return result
