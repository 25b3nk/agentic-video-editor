# Agentic Video Editor

An AI-powered parameterized video editing framework. Define sophisticated editing workflows in YAML, run them with natural-language AI agents that make creative decisions, and produce polished video output — all via a REST API.

## What It Does

- **Parameterized workflows** — Authors write YAML workflows with typed parameters (`name_text`, `beat_index`, `poster_style`, …). Users fill in values at job submission time.
- **18 built-in step types** — Transforms, overlays, effects, control flow, and AI steps covering the full editing lifecycle.
- **AI-driven decisions** — `agent_decision` steps call Claude to choose parameters at runtime (e.g. "find the best freeze frame before the beat drop").
- **External API steps** — `external_api` steps call Gemini Imagen or any HTTP service (e.g. generate an AI action poster from an extracted frame).
- **Expression system** — Steps can reference parameters, analysis results, and outputs from previous steps with `{{...}}` expressions.
- **Parallel video analysis** — Metadata, beat detection, and face detection run in parallel before execution starts.

## Architecture

```
app/
├── api/            # FastAPI routers (workflows CRUD, job lifecycle)
├── analysis/       # Parallel video analysis pipeline
│   ├── metadata.py     — FFprobe: duration, fps, resolution, codec
│   ├── beats.py        — librosa: beat timestamps + BPM
│   ├── faces.py        — MediaPipe: face bounding boxes per frame
│   └── pipeline.py     — Async orchestrator
├── engine/         # Workflow execution engine
│   ├── parser.py       — YAML parsing & parameter validation
│   ├── expressions.py  — {{...}} expression evaluator (safe, no eval)
│   ├── executor.py     — Job orchestration (analysis → steps → output)
│   ├── queue.py        — In-process async job queue
│   └── steps/          — 18 step type implementations
│       ├── transforms.py       (trim, crop, speed_change, freeze_frame, extract_frame)
│       ├── overlays.py         (add_text, add_image, add_audio, noop)
│       ├── effects.py          (shake, rotate, color_grade, particles, transition)
│       ├── control_flow.py     (group, conditional, loop)
│       └── ai.py               (agent_decision, external_api)
├── integrations/   # External API clients
│   ├── claude.py       — Anthropic SDK wrapper
│   └── gemini.py       — Gemini Imagen API wrapper
├── models/         # SQLAlchemy ORM models (Job, Workflow, VideoAnalysis)
├── schemas/        # Pydantic request/response schemas
├── db/session.py   # Async SQLAlchemy session factory
├── config.py       # Pydantic settings (reads from .env)
└── main.py         # FastAPI app + lifespan (starts job worker)
```

## Setup

### Requirements

- Python 3.11+
- PostgreSQL 15+
- FFmpeg (with `ffprobe`)

### Install

```bash
git clone https://github.com/25b3nk/agentic-video-editor
cd agentic-video-editor
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env — set DATABASE_URL, ANTHROPIC_API_KEY, GEMINI_API_KEY
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| `ANTHROPIC_API_KEY` | — | For `agent_decision` steps |
| `GEMINI_API_KEY` | — | For `external_api` steps targeting Gemini |
| `CLAUDE_MODEL` | `claude-opus-4-6` | Claude model used by agent steps |
| `UPLOAD_DIR` | `/tmp/video_editor/uploads` | Incoming video files |
| `WORK_DIR` | `/tmp/video_editor/work` | Per-job scratch space |
| `OUTPUT_DIR` | `/tmp/video_editor/outputs` | Finished videos |
| `MAX_CONCURRENT_JOBS` | `2` | Parallel job limit |
| `FFMPEG_BIN` / `FFPROBE_BIN` | `ffmpeg` / `ffprobe` | Binary paths |

### Database

```bash
alembic upgrade head
```

### Run

```bash
uvicorn app.main:app --reload
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

## API

### Workflows

| Method | Path | Description |
|---|---|---|
| `POST` | `/workflows` | Create workflow from YAML body |
| `GET` | `/workflows` | List all workflows |
| `GET` | `/workflows/{id}` | Get workflow + schema |
| `DELETE` | `/workflows/{id}` | Delete workflow |

### Jobs

| Method | Path | Description |
|---|---|---|
| `POST` | `/jobs` | Submit video + workflow ID + params |
| `GET` | `/jobs` | List jobs |
| `GET` | `/jobs/{id}` | Get job status + logs |
| `DELETE` | `/jobs/{id}` | Cancel / delete job |

### Health

```
GET /health  →  {"status": "ok", "version": "0.1.0"}
```

### Example: Submit a Job

```bash
# 1. Upload a workflow
curl -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d '{"name": "Action Poster Reveal", "yaml_content": "<yaml here>"}'

# 2. Submit a job
curl -X POST http://localhost:8000/jobs \
  -F "video=@input.mp4" \
  -F 'workflow_id=<id>' \
  -F 'params={"name_text": "JOHN DOE", "poster_style": "cinematic"}'

# 3. Poll for result
curl http://localhost:8000/jobs/<job-id>
```

## Workflow Schema

Workflows are YAML files. See [`docs/workflow_schema.md`](docs/workflow_schema.md) for the full specification and [`workflows/action_poster_reveal.yaml`](workflows/action_poster_reveal.yaml) for a complete example.

### Quick Example

```yaml
name: Simple Highlight Reel
description: Trim to the best beat, add a title card
version: "1.0"

parameters:
  - name: title_text
    type: string
    description: Title to overlay
  - name: beat_index
    type: integer
    default: 0
    min: 0

requires_analysis:
  - metadata
  - beat_detection

steps:
  - id: trim_to_beat
    type: trim
    params:
      start: 0
      end: "{{analysis.beat_detection.beats[{{beat_index}}]}}"

  - id: add_title
    type: add_text
    params:
      text: "{{title_text}}"
      position: center
      font_size: 72
      animation: fade_in
```

### Expression Syntax

| Expression | Resolves to |
|---|---|
| `{{param_name}}` | Workflow parameter value |
| `{{analysis.metadata.duration}}` | Analysis result field |
| `{{analysis.beat_detection.beats[0]}}` | First detected beat timestamp |
| `{{steps.my_step_id.output_path}}` | Output file from a previous step |
| `{{video.duration}}` | Shorthand for metadata duration |

## Running Tests

```bash
pytest
# or with coverage
pytest --cov=app --cov-report=term-missing
```

161 tests cover the parser, expression evaluator, all 18 step types, the analysis pipeline, and all API endpoints. All FFmpeg calls, AI API calls, and database writes are mocked — no real video or credentials required.

## Analysis Types

| Type | Library | Status |
|---|---|---|
| `metadata` | FFprobe | Implemented |
| `beat_detection` | librosa | Implemented |
| `face_detection` | MediaPipe | Implemented |
| `scene_detection` | PySceneDetect | Implemented |
| `silence_detection` | FFmpeg silencedetect | Planned |
| `transcription` | Whisper | Planned |
| `speaker_diarization` | pyannote-audio | Planned |

## Step Types

| Category | Steps |
|---|---|
| Transforms | `trim`, `crop`, `speed_change`, `freeze_frame`, `extract_frame` |
| Overlays | `add_text`, `add_image`, `add_audio`, `noop` |
| Effects | `shake`, `rotate`, `color_grade`, `particles`, `transition` |
| Control Flow | `group`, `conditional`, `loop` |
| AI / External | `agent_decision`, `external_api` |

## Project Status

The MVP is fully implemented and tested. Post-MVP items tracked in [`decisions.md`](decisions.md):

- [ ] Silence detection analysis
- [ ] Transcription (Whisper)
- [ ] Speaker diarization
- [ ] Redis + Celery job queue (replace in-process queue)
- [ ] Multiple output formats per job
- [ ] Workflow inheritance / templates
- [ ] Web UI
