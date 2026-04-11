"""Tests for the {{...}} expression evaluator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from app.engine import expressions
from app.engine.expressions import evaluate, resolve_path, resolve_step_inputs, resolve_value


# ── Minimal stub for ExecutionContext ─────────────────────────────────────────


@dataclass
class _FakeCtx:
    params: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    step_outputs: dict[str, Any] = field(default_factory=dict)


# ── resolve_path ─────────────────────────────────────────────────────────────


class TestResolvePath:
    def test_simple_key(self):
        assert resolve_path({"a": 1}, "a") == 1

    def test_nested_keys(self):
        obj = {"beat_detection": {"bpm": 128.0}}
        assert resolve_path(obj, "beat_detection.bpm") == 128.0

    def test_list_index(self):
        obj = {"beats": [0.5, 1.0, 1.5]}
        assert resolve_path(obj, "beats[1]") == 1.0

    def test_nested_list_index(self):
        obj = {"beat_detection": {"beats": [0.5, 1.0, 1.5]}}
        assert resolve_path(obj, "beat_detection.beats[2]") == 1.5

    def test_missing_key_raises(self):
        with pytest.raises(KeyError):
            resolve_path({"a": 1}, "b")

    def test_missing_index_raises(self):
        with pytest.raises(IndexError):
            resolve_path({"beats": [1.0]}, "beats[5]")


# ── evaluate: plain literals ──────────────────────────────────────────────────


class TestEvaluateLiterals:
    def test_integer_string(self):
        ctx = _FakeCtx()
        assert evaluate("42", ctx) == 42

    def test_float_string(self):
        ctx = _FakeCtx()
        assert evaluate("3.14", ctx) == 3.14

    def test_boolean_true(self):
        ctx = _FakeCtx()
        assert evaluate("true", ctx) is True

    def test_boolean_false(self):
        ctx = _FakeCtx()
        assert evaluate("false", ctx) is False

    def test_null(self):
        ctx = _FakeCtx()
        assert evaluate("null", ctx) is None

    def test_plain_string(self):
        ctx = _FakeCtx()
        assert evaluate("hello", ctx) == "hello"


# ── evaluate: single-token expressions ───────────────────────────────────────


class TestEvaluateSingleToken:
    def test_param_lookup(self):
        ctx = _FakeCtx(params={"name_text": "JOHN WICK"})
        assert evaluate("{{name_text}}", ctx) == "JOHN WICK"

    def test_param_integer(self):
        ctx = _FakeCtx(params={"beat_index": 2})
        assert evaluate("{{beat_index}}", ctx) == 2

    def test_param_boolean(self):
        ctx = _FakeCtx(params={"enable_particles": True})
        assert evaluate("{{enable_particles}}", ctx) is True

    def test_analysis_nested(self):
        ctx = _FakeCtx(analysis={"metadata": {"duration": 10.0}})
        assert evaluate("{{analysis.metadata.duration}}", ctx) == 10.0

    def test_analysis_list_index(self):
        ctx = _FakeCtx(analysis={"beat_detection": {"beats": [0.5, 1.0, 1.5]}})
        assert evaluate("{{analysis.beat_detection.beats[0]}}", ctx) == 0.5

    def test_video_alias(self):
        ctx = _FakeCtx(analysis={"metadata": {"width": 1920, "height": 1080}})
        assert evaluate("{{video.duration}}", _FakeCtx(analysis={"metadata": {"duration": 5.0}})) == 5.0

    def test_step_output(self):
        ctx = _FakeCtx(
            step_outputs={"generate_poster": {"poster_image_path": "/tmp/poster.png"}}
        )
        assert evaluate("{{steps.generate_poster.poster_image_path}}", ctx) == "/tmp/poster.png"

    def test_missing_param_raises(self):
        ctx = _FakeCtx()
        with pytest.raises(KeyError):
            evaluate("{{nonexistent_param}}", ctx)

    def test_whitespace_trimmed(self):
        ctx = _FakeCtx(params={"x": 99})
        assert evaluate("{{ x }}", ctx) == 99


# ── evaluate: arithmetic expressions ─────────────────────────────────────────


class TestEvaluateArithmetic:
    def test_beat_minus_offset(self):
        ctx = _FakeCtx(analysis={"beat_detection": {"beats": [2.0, 4.0]}})
        result = evaluate("{{analysis.beat_detection.beats[0]}} - 0.5", ctx)
        assert result == pytest.approx(1.5)

    def test_addition(self):
        ctx = _FakeCtx(params={"offset": 1.0})
        result = evaluate("{{offset}} + 2.0", ctx)
        assert result == pytest.approx(3.0)

    def test_multiplication(self):
        ctx = _FakeCtx(params={"duration": 3.0})
        result = evaluate("{{duration}} * 2", ctx)
        assert result == pytest.approx(6.0)

    def test_two_tokens(self):
        ctx = _FakeCtx(params={"a": 10.0, "b": 4.0})
        result = evaluate("{{a}} - {{b}}", ctx)
        assert result == pytest.approx(6.0)


# ── evaluate: comparison / conditional expressions ───────────────────────────


class TestEvaluateComparisons:
    def test_width_greater_than_height_true(self):
        ctx = _FakeCtx(analysis={"metadata": {"width": 1920, "height": 1080}})
        result = evaluate("{{analysis.metadata.width}} > {{analysis.metadata.height}}", ctx)
        assert result is True

    def test_width_greater_than_height_false(self):
        ctx = _FakeCtx(analysis={"metadata": {"width": 1080, "height": 1920}})
        result = evaluate("{{analysis.metadata.width}} > {{analysis.metadata.height}}", ctx)
        assert result is False

    def test_equality_numeric(self):
        ctx = _FakeCtx(params={"count": 3})
        result = evaluate("{{count}} == 3", ctx)
        assert result is True

    def test_not_equal_numeric(self):
        ctx = _FakeCtx(params={"count": 3})
        result = evaluate("{{count}} != 5", ctx)
        assert result is True

    def test_null_check(self):
        ctx = _FakeCtx(params={"music_file": None})
        result = evaluate("{{music_file}} != null", ctx)
        assert result is False


# ── evaluate: text interpolation ─────────────────────────────────────────────


class TestEvaluateInterpolation:
    def test_string_with_token(self):
        ctx = _FakeCtx(params={"style": "cinematic"})
        result = evaluate("Style: {{style}}", ctx)
        assert result == "Style: cinematic"

    def test_multiple_tokens_in_string(self):
        ctx = _FakeCtx(params={"w": 1920, "h": 1080})
        result = evaluate("{{w}}x{{h}}", ctx)
        assert result == "1920x1080"


# ── resolve_step_inputs ───────────────────────────────────────────────────────


class TestResolveStepInputs:
    def test_resolves_flat_dict(self):
        ctx = _FakeCtx(params={"dur": 5.0})
        result = resolve_step_inputs({"duration": "{{dur}}", "start": "0"}, ctx)
        assert result == {"duration": 5.0, "start": 0}

    def test_resolves_nested_dict(self):
        ctx = _FakeCtx(params={"x": 10})
        result = resolve_step_inputs({"pos": {"x": "{{x}}", "y": 20}}, ctx)
        assert result["pos"] == {"x": 10, "y": 20}

    def test_resolves_list(self):
        ctx = _FakeCtx(params={"v": 0.8})
        result = resolve_step_inputs({"volumes": ["{{v}}", 1.0]}, ctx)
        assert result["volumes"] == [0.8, 1.0]

    def test_passthrough_non_string(self):
        ctx = _FakeCtx()
        result = resolve_step_inputs({"count": 3, "flag": True}, ctx)
        assert result == {"count": 3, "flag": True}
