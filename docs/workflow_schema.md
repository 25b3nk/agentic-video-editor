# Workflow Schema Specification v1.0

## Overview

Workflows are defined in YAML and describe parameterized video editing recipes that can be applied to different source videos with AI-powered adaptation.

---

## Top-Level Structure

```yaml
version: "1.0"

metadata:
  name: string           # Required: Display name
  description: string    # Required: What this workflow does
  author: string         # Required: Creator identifier
  tags: [string]         # Optional: For discovery
  preview_thumbnail: url # Optional: Preview image

parameters: [Parameter]  # User-configurable inputs

requires_analysis: [AnalysisType]  # What analysis this workflow needs

steps: [Step]            # Ordered execution steps

output:                  # Output configuration
  format: string
  codec: string
  quality: string
```

---

## Parameters

Parameters allow users to customize workflow execution.

```yaml
parameters:
  - name: string              # Identifier (snake_case)
    type: string|integer|float|boolean|timestamp|file
    description: string       # Shown to user
    required: boolean         # Default: false
    default: any              # Default value if not provided

    # Type-specific constraints
    min: number               # For integer/float
    max: number               # For integer/float
    enum: [any]               # Allowed values
    pattern: string           # Regex for string validation
```

### Example

```yaml
parameters:
  - name: poster_style
    type: string
    default: "cinematic red atmosphere, action movie poster"
    description: "Style prompt for the generated poster"

  - name: name_text
    type: string
    required: true
    description: "Name to display on the poster"

  - name: beat_number
    type: integer
    default: 1
    min: 1
    max: 10
    description: "Which beat to trigger the poster reveal"
```

---

## Analysis Requirements

Declare what video analysis the workflow needs. The engine ensures analysis is complete before execution.

```yaml
requires_analysis:
  - metadata          # Basic: duration, resolution, fps
  - scene_detection   # Cut points
  - beat_detection    # Audio beats + BPM
  - transcription     # Speech-to-text with timestamps
  - speaker_diarization  # Who speaks when
  - silence_detection # Silent segments
  - face_detection    # Face bounding boxes
```

---

## Step Types

### Core Transforms

#### `trim`
Extract a time range from the video.

```yaml
- id: clip_intro
  type: trim
  inputs:
    start: timestamp|expression    # "00:00:05" or "{{beat_1}}"
    end: timestamp|expression
    # OR
    duration: float                # Alternative to end
```

#### `crop`
Spatial crop or aspect ratio adjustment.

```yaml
- id: make_vertical
  type: crop
  inputs:
    aspect_ratio: "9:16"           # Target ratio
    focus: center|face_detection   # What to keep centered
    # OR explicit coordinates
    x: integer
    y: integer
    width: integer
    height: integer
```

#### `speed_change`
Modify playback speed.

```yaml
- id: slow_mo
  type: speed_change
  inputs:
    factor: float                  # 0.5 = half speed, 2.0 = double
    maintain_pitch: boolean        # Keep audio pitch (default: true)
    range:                         # Optional: apply to specific range
      start: timestamp
      end: timestamp
```

#### `freeze_frame`
Hold a single frame for a duration.

```yaml
- id: poster_freeze
  type: freeze_frame
  inputs:
    at: timestamp|expression       # Which frame to freeze
    duration: float                # How long to hold (seconds)
```

#### `extract_frame`
Extract a frame as an image for external processing.

```yaml
- id: get_poster_frame
  type: extract_frame
  inputs:
    at: timestamp|expression
    format: png|jpg
  outputs:
    image_path: string             # Path to extracted image
```

---

### Overlays

#### `add_text`
Animated text overlay.

```yaml
- id: name_reveal
  type: add_text
  inputs:
    text: string|expression        # "{{name_text}}"
    position: bottom_center|top_left|custom
    x: integer                     # If position=custom
    y: integer

    # Styling
    font: string
    font_size: integer
    font_color: color
    background_color: color
    stroke_color: color
    stroke_width: integer

    # Animation
    animation: none|fade_in|slide_up|typewriter|glitch
    animation_duration: float

    # Timing
    start: timestamp
    end: timestamp
```

#### `add_image`
Image overlay (for the generated poster, logos, etc.).

```yaml
- id: overlay_poster
  type: add_image
  inputs:
    source: path|expression        # "{{steps.generate_poster.image_path}}"
    position: center|custom
    x: integer
    y: integer
    width: integer|auto
    height: integer|auto
    opacity: float                 # 0.0-1.0

    # Animation
    animation: none|fade_in|zoom_in|slide
    animation_duration: float

    # Timing
    start: timestamp
    end: timestamp
```

#### `add_audio`
Add music or sound effects.

```yaml
- id: add_beat_music
  type: add_audio
  inputs:
    source: path|url
    volume: float                  # 0.0-1.0
    start_at: timestamp            # When in video to start
    audio_offset: timestamp        # Offset within audio file
    fade_in: float
    fade_out: float
    duck_original: float           # Lower original audio to this level
```

#### `particles`
Particle effects overlay.

```yaml
- id: fire_particles
  type: particles
  inputs:
    effect: fire|sparks|smoke|dust|rain|snow|custom
    intensity: float               # 0.0-1.0
    color: color                   # Primary color
    position: fullscreen|bottom|custom

    # Timing
    start: timestamp
    end: timestamp
```

---

### Effects

#### `shake`
Camera shake effect.

```yaml
- id: impact_shake
  type: shake
  inputs:
    intensity: float               # 0.0-1.0
    frequency: float               # Shakes per second
    decay: boolean                 # Reduce over time

    start: timestamp
    end: timestamp
```

#### `rotate`
Rotation (static or animated).

```yaml
- id: subtle_rotation
  type: rotate
  inputs:
    angle: float                   # Degrees (static)
    # OR animated
    from_angle: float
    to_angle: float
    easing: linear|ease_in|ease_out|ease_in_out

    start: timestamp
    end: timestamp
```

#### `color_grade`
Color/atmosphere adjustment.

```yaml
- id: red_atmosphere
  type: color_grade
  inputs:
    preset: cinematic_red|noir|vintage|custom
    # OR manual adjustments
    brightness: float              # -1.0 to 1.0
    contrast: float
    saturation: float
    temperature: float             # Warm/cool
    tint: color                    # Color overlay
    tint_strength: float

    start: timestamp               # Optional: apply to range only
    end: timestamp
```

#### `transition`
Transitions between segments.

```yaml
- id: fade_to_poster
  type: transition
  inputs:
    effect: fade|dissolve|wipe|flash|glitch
    duration: float
    at: timestamp                  # When transition occurs
```

---

### Control Flow

#### `group`
Group steps together (sequential execution within group).

```yaml
- id: poster_effects
  type: group
  steps:
    - id: shake
      type: shake
      inputs: {...}
    - id: particles
      type: particles
      inputs: {...}
```

#### `conditional`
If/else branching based on conditions.

```yaml
- id: check_orientation
  type: conditional
  condition: "{{analysis.metadata.width}} > {{analysis.metadata.height}}"
  then:
    - id: crop_vertical
      type: crop
      inputs:
        aspect_ratio: "9:16"
  else:
    - id: skip_crop
      type: noop
```

#### `loop`
Repeat steps for each item in a collection.

```yaml
- id: cut_all_silences
  type: loop
  over: "{{analysis.silence_detection}}"
  as: silence
  steps:
    - id: speed_up_silence
      type: speed_change
      inputs:
        factor: 4.0
        range:
          start: "{{silence.start}}"
          end: "{{silence.end}}"
```

---

### AI/External

#### `agent_decision`
Claude decides parameter values based on analysis.

```yaml
- id: find_best_moment
  type: agent_decision
  prompt: |
    Analyze the video and find the best moment for the poster reveal.
    The video shows a person walking towards the camera.
    Find the frame where they are most centered and well-lit.
    Consider the beat timestamps: {{analysis.beat_detection.beats}}
  outputs:
    - name: reveal_timestamp
      type: timestamp
      description: "When to trigger the poster reveal"
    - name: reasoning
      type: string
      description: "Why this moment was chosen"
```

#### `external_api`
Call an external API (image generation, etc.).

```yaml
- id: generate_poster
  type: external_api
  service: gemini_imagen           # Registered service identifier
  inputs:
    image: "{{steps.get_poster_frame.image_path}}"
    prompt: "{{poster_style}}, dramatic lighting, movie poster"
    negative_prompt: "blurry, low quality"
  outputs:
    - name: image_path
      type: string
```

---

## Expressions

Use `{{...}}` syntax for dynamic values.

### Available Contexts

| Context | Description | Example |
|---------|-------------|---------|
| `{{param_name}}` | User parameter | `{{name_text}}` |
| `{{analysis.*}}` | Analysis results | `{{analysis.beat_detection.beats[0]}}` |
| `{{steps.id.output}}` | Previous step output | `{{steps.generate_poster.image_path}}` |
| `{{video.*}}` | Source video info | `{{video.duration}}` |

### Timestamp Expressions

```yaml
# Absolute
start: "00:01:30"
start: 90.5                        # Seconds

# Relative
start: "{{beat_1}} - 0.5"          # 0.5s before first beat

# From analysis
start: "{{analysis.beat_detection.beats[{{beat_number}}]}}"
```

---

## Output Configuration

```yaml
output:
  format: mp4|webm|mov|gif
  codec: h264|h265|vp9|prores
  quality: low|medium|high|lossless

  # Optional overrides
  resolution: 1080p|720p|4k|original
  fps: integer|original
  audio_codec: aac|opus|original
```
