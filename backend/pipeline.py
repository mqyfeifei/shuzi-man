import asyncio
import json
import uuid
from pathlib import Path

from .config import settings
from .db import connect, now
from .services import generate_video, synthesize


SOURCE_FILES = {"灵山景区": "灵山.mp4", "敦煌": "敦煌.mp4", "西湖": "西湖.mp4"}
_tasks: set[asyncio.Task] = set()


def available_sources() -> dict[str, dict]:
    return {
        spot: {"filename": filename, "available": (settings.data_dir / filename).is_file()}
        for spot, filename in SOURCE_FILES.items()
    }


def launch(job_id: int) -> None:
    task = asyncio.create_task(run(job_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def run(job_id: int) -> None:
    with connect() as db:
        job = db.execute("SELECT * FROM pipeline_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            return
        db.execute("UPDATE pipeline_jobs SET status='running',started_at=? WHERE id=?", (now(), job_id))
        item_ids = [r["id"] for r in db.execute("SELECT id FROM pipeline_items WHERE job_id=? ORDER BY id", (job_id,))]
    options = json.loads(job["options_json"])
    for item_id in item_ids:
        await _run_item(item_id, job["voice_id"], options)
        with connect() as db:
            counts = db.execute("""SELECT COUNT(*) completed_count,
              SUM(status='completed') success_count,SUM(status='failed') failed_count
              FROM pipeline_items WHERE job_id=? AND status IN ('completed','failed')""", (job_id,)).fetchone()
            db.execute("UPDATE pipeline_jobs SET completed_count=?,success_count=?,failed_count=? WHERE id=?",
                       (counts["completed_count"], counts["success_count"] or 0, counts["failed_count"] or 0, job_id))
    with connect() as db:
        failed = db.execute("SELECT failed_count FROM pipeline_jobs WHERE id=?", (job_id,)).fetchone()["failed_count"]
        db.execute("UPDATE pipeline_jobs SET status=?,completed_at=? WHERE id=?",
                   ("completed_with_errors" if failed else "completed", now(), job_id))


async def _run_item(item_id: int, voice_id: str, options: dict) -> None:
    audio_path = None
    try:
        with connect() as db:
            item = db.execute("""SELECT i.*,q.answer,q.scenic_spot_id,s.name spot_name
              FROM pipeline_items i JOIN qa_items q ON q.id=i.qa_id
              JOIN scenic_spots s ON s.id=q.scenic_spot_id WHERE i.id=?""", (item_id,)).fetchone()
            db.execute("UPDATE pipeline_items SET status='running',stage='tts' WHERE id=?", (item_id,))
        audio_name = f"qa_{item['qa_id']}_{uuid.uuid4().hex[:12]}.mp3"
        audio_path = settings.audio_dir / audio_name
        await synthesize(item["answer"], voice_id, audio_path)
        with connect() as db:
            cur = db.execute("""INSERT INTO audio_assets
              (qa_id,filename,relative_path,speaker_id,resource_id,created_at) VALUES (?,?,?,?,?,?)""",
              (item["qa_id"], audio_name, f"audio/{audio_name}", voice_id, settings.tts_cluster, now()))
            audio_id = cur.lastrowid
            db.execute("UPDATE pipeline_items SET audio_id=?,stage='video' WHERE id=?", (audio_id, item_id))

        source_name = SOURCE_FILES.get(item["spot_name"])
        source = settings.data_dir / source_name if source_name else None
        if not source or not source.is_file():
            raise RuntimeError(f"{item['spot_name']}尚未配置无声视频（期望 data/{source_name or '未映射.mp4'}）；音频已保留")
        with connect() as db:
            source_row = db.execute("SELECT id FROM source_assets WHERE relative_path=?", (source_name,)).fetchone()
            if source_row:
                source_id = source_row["id"]
            else:
                cur = db.execute("""INSERT INTO source_assets
                  (original_name,stored_name,relative_path,media_type,created_at) VALUES (?,?,?,?,?)""",
                  (source_name, source_name, source_name, "video/mp4", now()))
                source_id = cur.lastrowid
            cur = db.execute("INSERT INTO video_assets (qa_id,audio_id,source_id,status,created_at) VALUES (?,?,?,?,?)",
                             (item["qa_id"], audio_id, source_id, "processing", now()))
            video_id = cur.lastrowid
            db.execute("UPDATE pipeline_items SET video_id=?,source_path=? WHERE id=?", (video_id, source_name, item_id))
        video_name = f"avatar_{video_id}_{uuid.uuid4().hex[:10]}.mp4"
        remote_options = {**options, "output_name": Path(video_name).stem}
        result = await generate_video(source, audio_path, settings.video_dir / video_name, remote_options)
        with connect() as db:
            db.execute("""UPDATE video_assets SET filename=?,relative_path=?,status='completed',
              remote_response=?,completed_at=? WHERE id=?""",
              (video_name, f"videos/{video_name}", json.dumps(result, ensure_ascii=False), now(), video_id))
            db.execute("UPDATE pipeline_items SET status='completed',stage='completed',completed_at=? WHERE id=?", (now(), item_id))
    except Exception as exc:
        with connect() as db:
            row = db.execute("SELECT video_id FROM pipeline_items WHERE id=?", (item_id,)).fetchone()
            if row and row["video_id"]:
                db.execute("UPDATE video_assets SET status='failed',error_message=?,completed_at=? WHERE id=?",
                           (str(exc)[:1000], now(), row["video_id"]))
            db.execute("UPDATE pipeline_items SET status='failed',stage='failed',error_message=?,completed_at=? WHERE id=?",
                       (str(exc)[:1000], now(), item_id))
        if audio_path and audio_path.exists():
            with connect() as db:
                saved = db.execute("SELECT audio_id FROM pipeline_items WHERE id=?", (item_id,)).fetchone()["audio_id"]
            if not saved:
                audio_path.unlink(missing_ok=True)
