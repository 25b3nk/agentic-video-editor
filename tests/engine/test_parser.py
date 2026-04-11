"""Tests for the workflow YAML parser and parameter validator."""

from __future__ import annotations

import pytest

from app.engine.parser import WorkflowParseError, build_param_defaults, parse_workflow, validate_params


# ── parse_workflow: valid inputs ──────────────────────────────────────────────


class TestParseWorkflowValid:
    def test_minimal_workflow(self, minimal_workflow_yaml):
        doc = parse_workflow(minimal_workflow_yaml)
        assert doc["metadata"]["name"] == "Test Workflow"
        assert doc["metadata"]["author"] == "test"
        assert len(doc["steps"]) == 1

    def test_poster_workflow(self, poster_workflow_yaml):
        doc = parse_workflow(poster_workflow_yaml)
        assert doc["metadata"]["name"] == "Action Poster Reveal"
        assert len(doc["parameters"]) == 4
        assert len(doc["steps"]) == 2  # trim_intro + poster_segment

    def test_all_analysis_types_accepted(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
requires_analysis:
  - metadata
  - beat_detection
  - scene_detection
  - transcription
  - speaker_diarization
  - silence_detection
  - face_detection
steps:
  - id: noop
    type: noop
"""
        doc = parse_workflow(yaml)
        assert len(doc["requires_analysis"]) == 7

    def test_nested_group_steps(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
steps:
  - id: outer_group
    type: group
    steps:
      - id: inner_trim
        type: trim
        inputs:
          start: 0
          end: 5
"""
        doc = parse_workflow(yaml)
        group = doc["steps"][0]
        assert group["id"] == "outer_group"
        assert group["steps"][0]["id"] == "inner_trim"

    def test_conditional_then_else(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
steps:
  - id: check
    type: conditional
    condition: "{{width}} > {{height}}"
    then:
      - id: crop_it
        type: crop
        inputs:
          aspect_ratio: "9:16"
    else:
      - id: skip
        type: noop
"""
        doc = parse_workflow(yaml)
        cond = doc["steps"][0]
        assert cond["then"][0]["id"] == "crop_it"
        assert cond["else"][0]["id"] == "skip"

    def test_empty_steps_list(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
steps: []
"""
        doc = parse_workflow(yaml)
        assert doc["steps"] == []

    def test_no_parameters_key(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
steps:
  - id: s1
    type: noop
"""
        doc = parse_workflow(yaml)
        assert doc.get("parameters", []) == []


# ── parse_workflow: invalid inputs ────────────────────────────────────────────


class TestParseWorkflowInvalid:
    def test_not_yaml_mapping(self):
        with pytest.raises(WorkflowParseError, match="mapping"):
            parse_workflow("- just a list")

    def test_missing_metadata(self):
        with pytest.raises(WorkflowParseError, match="metadata"):
            parse_workflow("steps: []")

    def test_missing_metadata_name(self):
        yaml = """\
metadata:
  description: "d"
  author: "a"
steps: []
"""
        with pytest.raises(WorkflowParseError, match="name"):
            parse_workflow(yaml)

    def test_missing_steps(self):
        with pytest.raises(WorkflowParseError, match="steps"):
            parse_workflow("metadata:\n  name: T\n  description: d\n  author: a\n")

    def test_unknown_step_type(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
steps:
  - id: bad_step
    type: unknown_type_xyz
"""
        with pytest.raises(WorkflowParseError, match="unknown_type_xyz"):
            parse_workflow(yaml)

    def test_step_missing_id(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
steps:
  - type: trim
    inputs: {start: 0, end: 5}
"""
        with pytest.raises(WorkflowParseError, match="id"):
            parse_workflow(yaml)

    def test_step_missing_type(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
steps:
  - id: my_step
"""
        with pytest.raises(WorkflowParseError, match="type"):
            parse_workflow(yaml)

    def test_duplicate_step_ids(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
steps:
  - id: same_id
    type: noop
  - id: same_id
    type: noop
"""
        with pytest.raises(WorkflowParseError, match="Duplicate"):
            parse_workflow(yaml)

    def test_unknown_analysis_type(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
requires_analysis:
  - nonexistent_analysis
steps: []
"""
        with pytest.raises(WorkflowParseError, match="nonexistent_analysis"):
            parse_workflow(yaml)

    def test_invalid_parameter_type(self):
        yaml = """\
version: "1.0"
metadata:
  name: "T"
  description: "d"
  author: "a"
parameters:
  - name: bad_param
    type: imaginary_type
steps: []
"""
        with pytest.raises(WorkflowParseError, match="imaginary_type"):
            parse_workflow(yaml)

    def test_invalid_yaml_syntax(self):
        with pytest.raises(WorkflowParseError, match="Invalid YAML"):
            parse_workflow("key: [unclosed bracket")


# ── build_param_defaults ──────────────────────────────────────────────────────


class TestBuildParamDefaults:
    def test_extracts_defaults(self, minimal_workflow_yaml):
        doc = parse_workflow(minimal_workflow_yaml)
        defaults = build_param_defaults(doc)
        assert defaults == {"clip_duration": 5.0}

    def test_no_default_not_included(self):
        yaml = """\
version: "1.0"
metadata:
  name: T
  description: d
  author: a
parameters:
  - name: required_param
    type: string
    required: true
steps: []
"""
        doc = parse_workflow(yaml)
        defaults = build_param_defaults(doc)
        assert "required_param" not in defaults

    def test_empty_parameters(self):
        yaml = "version: '1.0'\nmetadata:\n  name: T\n  description: d\n  author: a\nsteps: []\n"
        doc = parse_workflow(yaml)
        assert build_param_defaults(doc) == {}


# ── validate_params ───────────────────────────────────────────────────────────


class TestValidateParams:
    def test_defaults_applied(self, minimal_workflow_yaml):
        doc = parse_workflow(minimal_workflow_yaml)
        result = validate_params(doc, {})
        assert result["clip_duration"] == 5.0

    def test_provided_overrides_default(self, minimal_workflow_yaml):
        doc = parse_workflow(minimal_workflow_yaml)
        result = validate_params(doc, {"clip_duration": 8.0})
        assert result["clip_duration"] == 8.0

    def test_required_param_missing_raises(self, poster_workflow_yaml):
        doc = parse_workflow(poster_workflow_yaml)
        with pytest.raises(WorkflowParseError, match="name_text"):
            validate_params(doc, {})

    def test_required_param_provided(self, poster_workflow_yaml):
        doc = parse_workflow(poster_workflow_yaml)
        result = validate_params(doc, {"name_text": "JOHN WICK"})
        assert result["name_text"] == "JOHN WICK"

    def test_integer_coercion(self, poster_workflow_yaml):
        doc = parse_workflow(poster_workflow_yaml)
        result = validate_params(doc, {"name_text": "X", "beat_index": "2"})
        assert result["beat_index"] == 2
        assert isinstance(result["beat_index"], int)

    def test_float_coercion(self, poster_workflow_yaml):
        doc = parse_workflow(poster_workflow_yaml)
        result = validate_params(doc, {"name_text": "X", "poster_duration": "4"})
        assert result["poster_duration"] == 4.0
        assert isinstance(result["poster_duration"], float)

    def test_boolean_coercion_string(self):
        yaml = """\
version: "1.0"
metadata:
  name: T
  description: d
  author: a
parameters:
  - name: flag
    type: boolean
    default: false
steps: []
"""
        doc = parse_workflow(yaml)
        result = validate_params(doc, {"flag": "true"})
        assert result["flag"] is True

    def test_min_violation_raises(self, poster_workflow_yaml):
        doc = parse_workflow(poster_workflow_yaml)
        with pytest.raises(WorkflowParseError, match=">= 0"):
            validate_params(doc, {"name_text": "X", "beat_index": -1})

    def test_max_violation_raises(self, poster_workflow_yaml):
        doc = parse_workflow(poster_workflow_yaml)
        with pytest.raises(WorkflowParseError, match="<= 5"):
            validate_params(doc, {"name_text": "X", "beat_index": 10})

    def test_enum_validation(self):
        yaml = """\
version: "1.0"
metadata:
  name: T
  description: d
  author: a
parameters:
  - name: mode
    type: string
    enum: [fast, slow, medium]
steps: []
"""
        doc = parse_workflow(yaml)
        with pytest.raises(WorkflowParseError, match="one of"):
            validate_params(doc, {"mode": "turbo"})

    def test_enum_valid_value(self):
        yaml = """\
version: "1.0"
metadata:
  name: T
  description: d
  author: a
parameters:
  - name: mode
    type: string
    enum: [fast, slow]
    default: fast
steps: []
"""
        doc = parse_workflow(yaml)
        result = validate_params(doc, {"mode": "slow"})
        assert result["mode"] == "slow"
