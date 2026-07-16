import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    db_path: Path = ROOT / "data" / "app.db"
    audio_dir: Path = ROOT / "data" / "audio"
    video_dir: Path = ROOT / "data" / "videos"
    final_video_dir: Path = ROOT / "data" / "final_videos"
    material_dir: Path = ROOT / "data" / "materials"
    tts_app_id: str = os.getenv("TTS_APP_ID", "")
    tts_access_token: str = os.getenv("TTS_ACCESS_TOKEN", "")
    tts_cluster: str = os.getenv("TTS_CLUSTER", "volcano_tts")
    tts_url: str = os.getenv("TTS_URL", "https://openspeech.bytedance.com/api/v1/tts")
    musetalk_base_url: str = os.getenv("MUSETALK_BASE_URL", "https://u754420-810d-5d42370e.westc.seetacloud.com:8443")
    timeout: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "600"))


settings = Settings()
