"""AI/External step executors: agent_decision, external_api."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.engine import expressions
from app.engine.steps.base import BaseStep, StepResult

if TYPE_CHECKING:
    from app.engine.executor import ExecutionContext

logger = logging.getLogger(__name__)


class AgentDecisionStep(BaseStep):
    """
    Calls Claude to decide parameter values based on analysis data.

    The step's `prompt` is a template with {{...}} expressions.
    Claude returns JSON matching the declared `outputs` schema.
    """

    step_type = "agent_decision"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        from app.integrations.claude import ask_claude

        prompt_template = step_def.get("prompt", "")
        prompt = expressions.evaluate(prompt_template, ctx)
        declared_outputs = step_def.get("outputs", [])

        # Build output schema description for Claude
        output_schema = "\n".join(
            f'- {o["name"]} ({o["type"]}): {o.get("description", "")}'
            for o in declared_outputs
        )
        system_prompt = (
            "You are an expert video editor AI assistant. "
            "Analyze the provided information and respond ONLY with a valid JSON object. "
            "Do not include any text outside the JSON. "
            f"Your response must include these fields:\n{output_schema}"
        )

        logger.info("Calling Claude for agent_decision step '%s'", step_def.get("id"))
        response_text = await ask_claude(system_prompt, str(prompt))

        # Parse JSON response
        try:
            outputs = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            import re
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                outputs = json.loads(json_match.group())
            else:
                raise RuntimeError(
                    f"Claude did not return valid JSON for step '{step_def.get('id')}': "
                    + response_text[:500]
                )

        # Coerce output types
        coerced = {}
        type_map = {o["name"]: o.get("type", "string") for o in declared_outputs}
        for name, value in outputs.items():
            t = type_map.get(name, "string")
            if t == "timestamp":
                coerced[name] = float(value)
            elif t == "integer":
                coerced[name] = int(value)
            elif t == "float":
                coerced[name] = float(value)
            elif t == "boolean":
                coerced[name] = bool(value)
            else:
                coerced[name] = value

        logger.info(
            "agent_decision '%s' outputs: %s",
            step_def.get("id"), json.dumps(coerced, indent=2)
        )
        return StepResult(outputs=coerced)


class ExternalApiStep(BaseStep):
    """
    Calls an external API service.

    Currently supported services:
      - gemini_imagen: Generate an image via Gemini Imagen API
    """

    step_type = "external_api"

    async def execute(self, step_def: dict, ctx: "ExecutionContext") -> StepResult:
        service = step_def.get("service", "")
        inputs = expressions.resolve_step_inputs(step_def.get("inputs", {}), ctx)
        declared_outputs = step_def.get("outputs", [])

        if service == "gemini_imagen":
            return await self._call_gemini_imagen(step_def, inputs, ctx, declared_outputs)
        else:
            raise ValueError(f"Unknown external API service: '{service}'")

    async def _call_gemini_imagen(
        self, step_def: dict, inputs: dict,
        ctx: "ExecutionContext", declared_outputs: list
    ) -> StepResult:
        from app.integrations.gemini import generate_image_from_photo

        image_path = inputs.get("image")
        prompt = inputs.get("prompt", "")
        negative_prompt = inputs.get("negative_prompt", "")

        if not image_path:
            raise ValueError("gemini_imagen step requires 'image' input")

        logger.info("Calling Gemini Imagen for step '%s'", step_def.get("id"))
        output_image = self.tmp_path(ctx, suffix=".png")
        await generate_image_from_photo(
            input_image_path=image_path,
            output_path=output_image,
            prompt=str(prompt),
            negative_prompt=str(negative_prompt),
        )

        return StepResult(outputs={"poster_image_path": str(output_image)})
