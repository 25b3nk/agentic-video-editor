# CLAUDE.md — Agentic Video Editor

Development guide for Claude Code working in this repository.

## Project Overview

An AI-powered video editing framework. Users define YAML workflows with typed parameters; the engine parses them, runs video analysis in parallel, then executes each step (FFmpeg transforms, AI calls, overlays, etc.) to produce output video.

**Key technologies:** FastAPI, SQLAlchemy async (PostgreSQL), Alembic, FFmpeg, librosa, MediaPipe, PySceneDetect, Anthropic SDK (Claude), Gemini Imagen API.

## Repository Layout

```
app/
  api/            — FastAPI routers: workflows.py, jobs.py
  analysis/       — Video analysis pipeline
    metadata.py       FFprobe wrapper
    beats.py          librosa beat detection
    faces.py          MediaPipe face detection
    scene.py          PySceneDetect scene detection
    pipeline.py       Async orchestrator (IMPLEMENTED set lives here)
  engine/         — Workflow execution
    parser.py         YAML → validated WorkflowDefinition dataclass
    expressions.py    {{...}} expression evaluator
    executor.py       WorkflowExecutor + ExecutionContext
    queue.py          In-process async job queue
    steps/
      base.py         BaseStep ABC
      registry.py     Maps type strings → BaseStep subclasses
      transforms.py   trim, crop, speed_change, freeze_frame, extract_frame
      overlays.py     add_text, add_image, add_audio, noop
      effects.py      shake, rotate, color_grade, particles, transition
      control_flow.py group, conditional, loop
      ai.py           agent_decision (Claude), external_api (Gemini)
      ffmpeg_utils.py shared FFmpeg command builders
  integrations/   — External API clients (claude.py, gemini.py)
  models/         — SQLAlchemy ORM: Job, Workflow, VideoAnalysis
  schemas/        — Pydantic schemas for API request/response
  db/session.py   — AsyncSessionLocal setup
  config.py       — Pydantic settings (reads .env)
  main.py         — FastAPI app + lifespan (starts job worker)
tests/
  engine/         — parser, expressions, steps (all mocked)
  analysis/       — metadata, pipeline
  api/            — workflows, jobs (in-memory SQLite)
  conftest.py     — shared fixtures
workflows/
  action_poster_reveal.yaml  — complete sample workflow
docs/
  workflow_schema.md         — full step-type reference
decisions.md                 — architectural decisions log
```

## Running Tests

```bash
pytest                              # all 161 tests
pytest tests/engine/               # engine-only
pytest tests/api/test_jobs.py -v   # specific file
pytest --cov=app --cov-report=term-missing
```

No real video files, database, or API keys needed — all external calls are mocked via `unittest.mock` / `pytest-mock` / `AsyncMock`.

## Running the App

```bash
cp .env.example .env   # fill in DATABASE_URL, ANTHROPIC_API_KEY, GEMINI_API_KEY
alembic upgrade head
uvicorn app.main:app --reload
```

Docs auto-generated at `http://localhost:8000/docs`.

## Key Patterns

### Adding a New Analysis Type

1. Create `app/analysis/<type>.py` with an `async def detect_<type>(video_path: Path) -> dict` function.
2. Add the type string to `IMPLEMENTED` in `app/analysis/pipeline.py`.
3. Add a dispatch branch in `run_analysis()` in `pipeline.py`.
4. Add tests in `tests/analysis/`.
5. Update the `Analysis Types` table in `README.md`.

### Adding a New Step Type

1. Create (or add to an existing module in) `app/engine/steps/`.
2. Subclass `BaseStep` and implement `async def execute(self, params, context) -> StepResult`.
3. Register the type string in `app/engine/steps/registry.py`.
4. Add tests in `tests/engine/steps/`.
5. Document the params in `docs/workflow_schema.md`.

### Expression System

`{{expression}}` is evaluated by `app/engine/expressions.py`. Supported:

- `{{param_name}}` — workflow parameter
- `{{analysis.beat_detection.beats[0]}}` — nested analysis result
- `{{steps.<step_id>.<output_key>}}` — output from a previous step
- `{{video.duration}}` — shorthand for `analysis.metadata.duration`
- Arithmetic and comparison operators via `ast` (safe, no `eval`)

### FFmpeg Usage

All FFmpeg/FFprobe calls go through `app/engine/steps/ffmpeg_utils.py` helpers or direct `asyncio.create_subprocess_exec` calls. **Never shell-interpolate user input** — always pass arguments as a list.

### AI Integrations

- `agent_decision` steps use `app/integrations/claude.py` → Anthropic SDK.
- `external_api` steps use `app/integrations/gemini.py` for image generation, or raw `httpx` for arbitrary HTTP.
- Always mock these in tests (`AsyncMock` the SDK methods).

## Coding Conventions

- **Async throughout** — all I/O is `async/await`; no `time.sleep`, no blocking calls in the hot path.
- **Type hints everywhere** — use `from __future__ import annotations` at top of each file.
- **Pydantic for settings** — add new config via `app/config.py`, access via `from app.config import settings`.
- **No bare `except`** — catch specific exceptions; log with `logger.error(...)`.
- **Tests mirror source** — `tests/analysis/test_scene.py` for `app/analysis/scene.py`, etc.
- **No `print` in app code** — use `logging.getLogger(__name__)`.

## Current Implementation Status

### Implemented
- All 18 step types (transforms, overlays, effects, control flow, AI)
- Analysis: metadata (FFprobe), beat detection (librosa), face detection (MediaPipe), scene detection (PySceneDetect)
- Full API (workflow CRUD, job lifecycle)
- In-process async job queue
- Expression evaluator
- Alembic DB migrations
- 161-test suite

### Post-MVP Roadmap (in priority order)
1. Silence detection (`FFmpeg silencedetect` filter)
2. Transcription (`openai-whisper` — heavy dep, currently commented out in requirements.txt)
3. Speaker diarization (`pyannote-audio`)
4. Redis + Celery job queue (replace in-process queue for production)
5. Multiple output formats per job
6. Workflow inheritance / templates
7. Web UI + workflow marketplace

## Branch Strategy

Active development branch: `claude/add-readme-docs-RZe8E`
Main branch: `main`

Always develop on the designated branch and push there. Do not push directly to `main`.

## Environment Variables

See `.env.example` for the full list. Critical ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL async connection string |
| `ANTHROPIC_API_KEY` | Required for `agent_decision` steps |
| `GEMINI_API_KEY` | Required for `external_api` → Gemini steps |
| `CLAUDE_MODEL` | Claude model ID (default: `claude-opus-4-6`) |
| `MAX_CONCURRENT_JOBS` | Job queue parallelism (default: `2`) |
