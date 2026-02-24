# Architectural Decisions Log

## Decision 001: Workflow Schema Design
**Date:** 2025-02-01
**Status:** In Progress

### Context
Building an agentic video editor where users create, share, and execute AI-powered editing workflows.

### MVP Target Use Case
"Action Poster Reveal" trend:
1. Input video: person walking into frame / towards camera
2. At beat drop: freeze frame → stylized action poster (generated via Gemini Imagen)
3. Poster has motion effects: shake, rotation, fire particles
4. Animated text overlay with name

### Decisions Made

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| 1 | Step nesting | ✅ Supported | Group related operations, enable loops |
| 2 | Conditional branching | ✅ Supported | `if/else` for adaptive workflows |
| 3 | Multiple outputs | ❌ MVP = single output | Simplifies execution engine |
| 4 | Workflow inheritance | ❌ Post-MVP | Nice-to-have, not critical |
| 5 | Parameter validation | `type/min/max/enum` | Sufficient for MVP |
| 6 | External API steps | ✅ Required | Need Gemini integration for image gen |
| 7 | Audio analysis | ✅ Required | Beat detection for sync |

### Step Types (MVP)

**Core Transforms:**
- `trim` — Extract time range
- `crop` — Spatial crop / aspect ratio
- `speed_change` — Speed up/slow down
- `freeze_frame` — Hold a single frame

**Overlays:**
- `add_text` — Text with animation
- `add_image` — Image overlay
- `add_audio` — Music/sound overlay
- `particles` — Fire, sparks, etc.

**Effects:**
- `shake` — Camera shake effect
- `rotate` — Rotation (static or animated)
- `color_grade` — Color/atmosphere adjustment
- `transition` — Fade, wipe, etc.

**Control Flow:**
- `group` — Nested steps (sequential)
- `conditional` — If/else branching
- `loop` — Repeat over detected items (scenes, beats, etc.)

**AI/External:**
- `agent_decision` — Claude decides parameters
- `external_api` — Call external service (Gemini, etc.)
- `extract_frame` — Get frame as image for processing

---

## Decision 002: Analysis Pipeline Components
**Date:** 2025-02-01
**Status:** Decided

### Required Analysis Types

| Analysis | Library/Tool | Output |
|----------|--------------|--------|
| Metadata | FFprobe | duration, fps, resolution, codec |
| Scene detection | PySceneDetect | list of cut timestamps |
| Beat detection | librosa | list of beat timestamps + BPM |
| Transcription | Whisper | text + word-level timestamps |
| Speaker diarization | pyannote-audio | speaker segments |
| Silence detection | FFmpeg silencedetect | silence ranges |
| Face detection | MediaPipe / YOLO | face bounding boxes per frame |

For MVP "action poster" workflow, critical ones are:
- ✅ Metadata
- ✅ Beat detection (for sync)
- ✅ Face detection (optional, for framing)

---

## Decision 003: Tech Stack
**Date:** 2025-02-01
**Status:** Decided

- **Framework:** FastAPI
- **Database:** PostgreSQL + pgvector
- **Migrations:** Alembic
- **Video processing:** FFmpeg
- **Audio analysis:** librosa
- **Transcription:** Whisper (openai-whisper or faster-whisper)
- **AI reasoning:** Claude API (Anthropic)
- **Image generation:** Gemini Imagen API
- **Background jobs:** Simple in-process queue (MVP), Redis + Celery (later)

---

## Decision 004: MVP Sample Workflow
**Date:** 2025-02-01
**Status:** Designed

### "Action Poster Reveal" Workflow

**Trend Description:**
1. Person walks into frame / towards camera
2. Beat drop triggers freeze frame
3. Freeze transforms into AI-generated action movie poster
4. Poster has shake effect, fire particles, subtle rotation
5. Animated text shows the name

**Workflow Phases:**
```
┌─────────────────────────────────────────────────────────────────┐
│ PHASE 1: Analysis                                               │
│   └─> Agent finds best freeze moment based on beats            │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 2: Frame Extraction                                       │
│   └─> Extract frame at freeze_timestamp as PNG                 │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 3: Poster Generation                                      │
│   └─> Send frame to Gemini Imagen with style prompt            │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 4: Video Assembly                                         │
│   ├─> Trim intro (walking segment)                              │
│   ├─> Crop to vertical if needed                                │
│   ├─> Create poster segment:                                    │
│   │     ├─ Freeze frame base                                    │
│   │     ├─ Overlay generated poster                             │
│   │     ├─ Apply red color grade                                │
│   │     ├─ Camera shake effect                                  │
│   │     ├─ Subtle rotation                                      │
│   │     ├─ Fire particles (optional)                            │
│   │     └─ Animated name text                                   │
│   └─> Flash transition between intro and poster                 │
├─────────────────────────────────────────────────────────────────┤
│ PHASE 5: Audio                                                  │
│   └─> Overlay music if provided, duck original audio            │
└─────────────────────────────────────────────────────────────────┘
```

**External Dependencies:**
- Gemini Imagen API for poster generation
- librosa for beat detection
- FFmpeg for all video processing
