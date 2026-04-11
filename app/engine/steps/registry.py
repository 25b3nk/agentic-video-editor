"""Step type registry — maps step type strings to executor instances."""

from __future__ import annotations

from app.engine.steps.ai import AgentDecisionStep, ExternalApiStep
from app.engine.steps.base import BaseStep
from app.engine.steps.control_flow import ConditionalStep, GroupStep, LoopStep
from app.engine.steps.effects import ColorGradeStep, ParticlesStep, RotateStep, ShakeStep, TransitionStep
from app.engine.steps.overlays import AddAudioStep, AddImageStep, AddTextStep, NoopStep
from app.engine.steps.transforms import (
    CropStep, ExtractFrameStep, FreezeFrameStep, SpeedChangeStep, TrimStep,
)

_REGISTRY: dict[str, BaseStep] = {}


def _register(*step_classes: type[BaseStep]) -> None:
    for cls in step_classes:
        instance = cls()
        _REGISTRY[instance.step_type] = instance


_register(
    # Transforms
    TrimStep, CropStep, SpeedChangeStep, FreezeFrameStep, ExtractFrameStep,
    # Overlays
    AddTextStep, AddImageStep, AddAudioStep, NoopStep,
    # Effects
    ShakeStep, RotateStep, ColorGradeStep, TransitionStep, ParticlesStep,
    # Control flow
    GroupStep, ConditionalStep, LoopStep,
    # AI
    AgentDecisionStep, ExternalApiStep,
)


def get_step_executor(step_type: str) -> BaseStep:
    executor = _REGISTRY.get(step_type)
    if executor is None:
        raise ValueError(f"Unknown step type: '{step_type}'")
    return executor
