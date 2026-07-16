import json
import mimetypes
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import connect, init_db, now, rows
from .services import generate_video, musetalk_health, synthesize
from .voices import DEFAULT_VOICE_ID, VOICE_IDS, VOICES
from .pipeline import available_sources, launch
from .catalog import generate_video_catalog
from .final_videos import organize_final_videos

app = FastAPI(title="景区数字人工具", version="1.0.0")
init_db()


@app.on_event("startup")
async def resume_pipeline_queue():
    launch()


def fail(exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc
    raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/scenic-spots")
def scenic_spots():
    return rows("SELECT id,name FROM scenic_spots ORDER BY id")


@app.get("/api/tts/voices")
def tts_voices():
    return {"default": DEFAULT_VOICE_ID, "items": VOICES}


@app.get("/api/scenic-spots/{spot_id}/qa")
def qa_list(spot_id: int):
    return rows("""SELECT q.id,q.question,q.answer,q.question_en,q.answer_en,
      (SELECT COUNT(*) FROM audio_assets a WHERE a.qa_id=q.id) audio_count,
      (SELECT COUNT(*) FROM video_assets v WHERE v.qa_id=q.id AND v.status='completed') video_count
      FROM qa_items q WHERE q.scenic_spot_id=? ORDER BY q.id""", (spot_id,))


class PipelineRequest(BaseModel):
    qa_ids: list[int] = Field(min_length=1)
    voice_id: str = DEFAULT_VOICE_ID
    language: str = "zh"
    enhance: bool = True
    gfpgan_weight: float = Field(default=0.5, ge=0, le=1)
    bbox_shift: int = 0
    extra_margin: int = Field(default=10, ge=0, le=40)
    parsing_mode: str = "jaw"
    fps: int = Field(default=25, ge=1, le=60)
    batch_size: int = Field(default=8, ge=1, le=32)


@app.get("/api/pipeline/config")
def pipeline_config():
    return {"sources": available_sources()}


@app.get("/api/video-catalog/export")
def export_video_catalog(request: Request):
    path, _ = generate_video_catalog(str(request.base_url))
    return FileResponse(path, media_type="text/html; charset=utf-8",
                        headers={"Content-Disposition": 'inline; filename="video_catalog.html"'})


@app.post("/api/final-videos/organize")
def organize_videos():
    return organize_final_videos()


@app.post("/api/pipeline/jobs", status_code=202)
async def create_pipeline_job(request: PipelineRequest):
    if request.language not in {"zh", "en"}:
        raise HTTPException(400, "仅支持中文或英文")
    if request.voice_id not in VOICE_IDS:
        raise HTTPException(400, "不支持的音色")
    if request.parsing_mode not in {"jaw", "raw"}:
        raise HTTPException(400, "不支持的面部融合模式")
    qa_ids = list(dict.fromkeys(request.qa_ids))
    placeholders = ",".join("?" for _ in qa_ids)
    with connect() as db:
        found = db.execute(f"SELECT id FROM qa_items WHERE id IN ({placeholders})", qa_ids).fetchall()
        if len(found) != len(qa_ids):
            raise HTTPException(400, "选择中包含不存在的回答")
        if request.language == "en":
            translated = db.execute(f"""SELECT COUNT(*) count FROM qa_items
              WHERE id IN ({placeholders}) AND question_en IS NOT NULL AND answer_en IS NOT NULL""", qa_ids).fetchone()["count"]
            if translated != len(qa_ids):
                raise HTTPException(400, "选择中包含尚无英文版本的问答")
        options = request.model_dump(exclude={"qa_ids", "voice_id", "language"})
        options = {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in options.items()}
        cur = db.execute("""INSERT INTO pipeline_jobs
          (voice_id,status,total_count,options_json,created_at,language) VALUES (?,?,?,?,?,?)""",
          (request.voice_id, "queued", len(qa_ids), json.dumps(options), now(), request.language))
        job_id = cur.lastrowid
        db.executemany("""INSERT INTO pipeline_items
          (job_id,qa_id,status,stage,created_at) VALUES (?,?,'queued','waiting',?)""",
          [(job_id, qa_id, now()) for qa_id in qa_ids])
    launch(job_id)
    return {"id": job_id, "status": "queued", "total_count": len(qa_ids)}


@app.get("/api/pipeline/jobs")
def pipeline_jobs():
    return rows("""SELECT j.*,
      CASE WHEN j.status='queued' THEN
        (SELECT COUNT(*) FROM pipeline_jobs q WHERE q.status='queued' AND q.id<=j.id)
      END queue_position
      FROM pipeline_jobs j ORDER BY j.id DESC LIMIT 20""")


@app.get("/api/pipeline/jobs/{job_id}")
def pipeline_job(job_id: int):
    jobs = rows("SELECT * FROM pipeline_jobs WHERE id=?", (job_id,))
    if not jobs:
        raise HTTPException(404, "流水线任务不存在")
    items = rows("""SELECT i.*,
      CASE WHEN j.language='en' THEN q.question_en ELSE q.question END question,
      s.name spot_name,a.relative_path audio_path,
      v.relative_path video_path FROM pipeline_items i JOIN qa_items q ON q.id=i.qa_id
      JOIN pipeline_jobs j ON j.id=i.job_id
      JOIN scenic_spots s ON s.id=q.scenic_spot_id
      LEFT JOIN audio_assets a ON a.id=i.audio_id LEFT JOIN video_assets v ON v.id=i.video_id
      WHERE i.job_id=? ORDER BY i.id""", (job_id,))
    return {**jobs[0], "items": items}


@app.get("/api/qa/{qa_id}/assets")
def qa_assets(qa_id: int):
    audio = rows("SELECT * FROM audio_assets WHERE qa_id=? ORDER BY id DESC", (qa_id,))
    video = rows("""SELECT v.*,s.original_name source_name FROM video_assets v
      JOIN source_assets s ON s.id=v.source_id WHERE v.qa_id=? ORDER BY v.id DESC""", (qa_id,))
    return {"audio": audio, "video": video}


@app.post("/api/qa/{qa_id}/tts")
async def create_tts(qa_id: int, voice_id: str = Form(DEFAULT_VOICE_ID), language: str = Form("zh")):
    if language not in {"zh", "en"}:
        raise HTTPException(400, "仅支持中文或英文")
    if voice_id not in VOICE_IDS:
        raise HTTPException(400, "不支持的音色，请从音色列表中选择")
    with connect() as db:
        qa = db.execute("SELECT * FROM qa_items WHERE id=?", (qa_id,)).fetchone()
    if not qa:
        raise HTTPException(404, "问答不存在")
    text = qa["answer_en"] if language == "en" else qa["answer"]
    if not text:
        raise HTTPException(400, "该问答尚无英文版本")
    filename = f"qa_{qa_id}_{uuid.uuid4().hex[:12]}.mp3"
    output_dir = settings.audio_dir / language
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / filename
    try:
        await synthesize(text, voice_id, output)
        with connect() as db:
            cur = db.execute("""INSERT INTO audio_assets
              (qa_id,filename,relative_path,speaker_id,resource_id,created_at,language)
              VALUES (?,?,?,?,?,?,?)""",
              (qa_id, filename, f"audio/{language}/{filename}", voice_id, settings.tts_cluster, now(), language))
            audio_id = cur.lastrowid
        return {"id": audio_id, "filename": filename, "voice_id": voice_id, "language": language, "url": f"/media/audio/{language}/{filename}"}
    except Exception as exc:
        output.unlink(missing_ok=True)
        fail(exc)


ALLOWED_SOURCE = {".jpg", ".jpeg", ".png", ".mp4"}


@app.post("/api/materials")
async def upload_material(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SOURCE:
        raise HTTPException(400, "仅支持 JPG、JPEG、PNG 或 MP4 素材")
    stored = f"{uuid.uuid4().hex}{suffix}"
    target = settings.material_dir / stored
    size = 0
    with target.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > 200 * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise HTTPException(413, "素材不能超过 200MB")
            out.write(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "不能上传空文件")
    with connect() as db:
        cur = db.execute("""INSERT INTO source_assets
          (original_name,stored_name,relative_path,media_type,created_at) VALUES (?,?,?,?,?)""",
          (file.filename, stored, f"materials/{stored}", file.content_type or mimetypes.guess_type(stored)[0] or "", now()))
        asset_id = cur.lastrowid
    return {"id": asset_id, "name": file.filename, "url": f"/media/materials/{stored}"}


@app.get("/api/materials")
def materials():
    return rows("SELECT id,original_name,stored_name,media_type,created_at FROM source_assets ORDER BY id DESC")


@app.get("/api/musetalk/health")
async def health():
    try:
        return await musetalk_health()
    except Exception as exc:
        fail(exc)


@app.post("/api/videos")
async def create_video(
    qa_id: int = Form(...), audio_id: int = Form(...), source_id: int = Form(...),
    enhance: bool = Form(True), gfpgan_weight: float = Form(0.5), bbox_shift: int = Form(0),
    extra_margin: int = Form(10), parsing_mode: str = Form("jaw"), fps: int = Form(25), batch_size: int = Form(8),
):
    if not 0 <= gfpgan_weight <= 1 or not 0 <= extra_margin <= 40 or parsing_mode not in {"jaw", "raw"} or not 1 <= fps <= 60 or not 1 <= batch_size <= 32:
        raise HTTPException(400, "数字人参数超出允许范围")
    with connect() as db:
        audio = db.execute("SELECT * FROM audio_assets WHERE id=? AND qa_id=?", (audio_id, qa_id)).fetchone()
        source = db.execute("SELECT * FROM source_assets WHERE id=?", (source_id,)).fetchone()
        if not audio or not source:
            raise HTTPException(404, "音频、素材或问答关系无效")
        cur = db.execute("INSERT INTO video_assets (qa_id,audio_id,source_id,status,created_at) VALUES (?,?,?,?,?)",
                         (qa_id, audio_id, source_id, "processing", now()))
        video_id = cur.lastrowid
    filename = f"avatar_{video_id}_{uuid.uuid4().hex[:10]}.mp4"
    options = {"enhance": str(enhance).lower(), "gfpgan_weight": str(gfpgan_weight), "bbox_shift": str(bbox_shift),
               "extra_margin": str(extra_margin), "parsing_mode": parsing_mode, "left_cheek_width": "90",
               "right_cheek_width": "90", "fps": str(fps), "batch_size": str(batch_size), "output_name": Path(filename).stem}
    try:
        language = audio["language"]
        output_dir = settings.video_dir / language
        output_dir.mkdir(parents=True, exist_ok=True)
        result = await generate_video(settings.data_dir / source["relative_path"], settings.data_dir / audio["relative_path"], output_dir / filename, options)
        with connect() as db:
            db.execute("""UPDATE video_assets SET filename=?,relative_path=?,status='completed',remote_response=?,completed_at=? WHERE id=?""",
                       (filename, f"videos/{language}/{filename}", json.dumps(result, ensure_ascii=False), now(), video_id))
            db.execute("UPDATE video_assets SET language=? WHERE id=?", (language, video_id))
        return {"id": video_id, "filename": filename, "language": language,
                "url": f"/media/videos/{language}/{filename}", "status": "completed"}
    except Exception as exc:
        with connect() as db:
            db.execute("UPDATE video_assets SET status='failed',error_message=?,completed_at=? WHERE id=?", (str(exc)[:1000], now(), video_id))
        fail(exc)


@app.get("/media/{kind}/{filename:path}")
def media(kind: str, filename: str):
    folders = {"audio": settings.audio_dir, "videos": settings.video_dir, "materials": settings.material_dir}
    relative = Path(filename)
    if kind not in folders or relative.is_absolute() or ".." in relative.parts:
        raise HTTPException(404)
    path = folders[kind] / relative
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


app.mount("/", StaticFiles(directory=settings.root / "static", html=True), name="static")
