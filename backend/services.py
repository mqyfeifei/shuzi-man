import base64
import json
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urljoin

import httpx

from .config import settings


class ServiceError(RuntimeError):
    pass


def _extract_tts_audio(payload: dict) -> bytes:
    if payload.get("code") not in (None, 0, 3000):
        raise ServiceError(f"语音合成失败：{payload.get('message') or payload.get('msg') or payload}")
    data = payload.get("data")
    if not isinstance(data, str) or not data:
        raise ServiceError(f"语音合成接口未返回音频数据：{payload.get('message') or '未知错误'}")
    try:
        return base64.b64decode(data, validate=True)
    except (ValueError, TypeError) as exc:
        raise ServiceError("语音合成接口返回了无效的 Base64 音频") from exc


async def synthesize(text: str, voice_id: str, output: Path) -> None:
    if not settings.tts_app_id or not settings.tts_access_token:
        raise ServiceError("尚未配置 TTS_APP_ID 或 TTS_ACCESS_TOKEN")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer;{settings.tts_access_token}"}
    payload = {
        "app": {"appid": settings.tts_app_id, "token": settings.tts_access_token, "cluster": settings.tts_cluster},
        "user": {"uid": "scenic-avatar-tool"},
        "audio": {"voice_type": voice_id, "encoding": "mp3", "speed_ratio": 1.0, "volume_ratio": 1.0, "pitch_ratio": 1.0},
        "request": {"reqid": str(uuid.uuid4()), "text": text, "text_type": "plain", "operation": "query", "with_frontend": 1, "frontend_type": "unitTson"},
    }
    # if voice_info["lang"] == "en":
    #     payload["audio"]["language"] = "en"
    async with httpx.AsyncClient(timeout=settings.timeout) as client:
        response = await client.post(settings.tts_url, headers=headers, json=payload)
    if response.status_code >= 400:
        raise ServiceError(f"语音合成接口 HTTP {response.status_code}：{response.text[:300]}")
    try:
        result = response.json()
    except json.JSONDecodeError as exc:
        raise ServiceError("语音合成接口返回的不是有效 JSON") from exc
    audio = _extract_tts_audio(result)
    temp = output.with_suffix(".tmp")
    temp.write_bytes(audio)
    temp.replace(output)


async def musetalk_health() -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{settings.musetalk_base_url.rstrip('/')}/health")
    response.raise_for_status()
    return response.json()


async def generate_video(source: Path, audio: Path, output: Path, options: dict) -> dict:
    base = settings.musetalk_base_url.rstrip("/") + "/"
    source_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    audio_type = mimetypes.guess_type(audio.name)[0] or "audio/mpeg"
    async with httpx.AsyncClient(timeout=settings.timeout) as client:
        with source.open("rb") as sf, audio.open("rb") as af:
            response = await client.post(
                urljoin(base, "generate"),
                files={"source": (source.name, sf, source_type), "audio": (audio.name, af, audio_type)},
                data=options,
            )
        if response.status_code >= 400:
            raise ServiceError(f"MuseTalk 生成失败（HTTP {response.status_code}）：{response.text[:500]}")
        result = response.json()
        download_url = result.get("download_url")
        if not download_url:
            raise ServiceError("MuseTalk 响应缺少 download_url")
        async with client.stream("GET", urljoin(base, download_url.lstrip("/"))) as video:
            video.raise_for_status()
            temp = output.with_suffix(".tmp")
            with temp.open("wb") as handle:
                async for chunk in video.aiter_bytes(1024 * 1024):
                    handle.write(chunk)
            temp.replace(output)
    return result
