from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/video_editor"

    # Storage paths
    upload_dir: Path = Path("/tmp/video_editor/uploads")
    work_dir: Path = Path("/tmp/video_editor/work")
    output_dir: Path = Path("/tmp/video_editor/outputs")

    # AI APIs
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # Model config
    claude_model: str = "claude-opus-4-6"

    # FFmpeg binaries
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    # Job queue
    max_concurrent_jobs: int = 2

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False

    def ensure_dirs(self) -> None:
        for d in (self.upload_dir, self.work_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
