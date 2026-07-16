from html import escape
from pathlib import Path

from .config import settings
from .db import rows, now
from .voices import VOICES


def generate_video_catalog(base_url: str) -> tuple[Path, int]:
    records = rows("""SELECT v.id video_id,v.filename video_filename,v.relative_path video_path,
      v.completed_at,q.question,q.answer,q.question_en,q.answer_en,
      COALESCE(v.language,'zh') language,s.name spot_name,
      a.id audio_id,a.filename audio_filename,a.relative_path audio_path,a.speaker_id
      FROM video_assets v
      JOIN qa_items q ON q.id=v.qa_id
      JOIN scenic_spots s ON s.id=q.scenic_spot_id
      JOIN audio_assets a ON a.id=v.audio_id
      WHERE v.status='completed' AND v.relative_path IS NOT NULL
      ORDER BY s.id,q.id,v.id""")
    voice_names = {voice["id"]: voice["name"] for voice in VOICES}
    root = base_url.rstrip("/")
    cards = []
    for item in records:
        question = item["question_en"] if item["language"] == "en" else item["question"]
        answer = item["answer_en"] if item["language"] == "en" else item["answer"]
        audio_url = f"{root}/media/{item['audio_path']}"
        video_url = f"{root}/media/{item['video_path']}"
        audio_local = settings.data_dir / item["audio_path"]
        video_local = settings.data_dir / item["video_path"]
        voice = voice_names.get(item["speaker_id"], item["speaker_id"])
        cards.append(f"""
        <article>
          <div class="top"><span>{escape(item['spot_name'])}</span><b>视频 #{item['video_id']}</b></div>
          <h2>{escape(question or '')}</h2>
          <p class="answer">{escape(answer or '')}</p>
          <dl>
            <dt>合成音色</dt><dd>{escape(voice)} <code>{escape(item['speaker_id'])}</code></dd>
            <dt>音频</dt><dd><a href="{escape(audio_url)}" target="_blank">播放 / 打开音频</a><br><code>{escape(str(audio_local.resolve()))}</code></dd>
            <dt>视频</dt><dd><a href="{escape(video_url)}" target="_blank">播放 / 打开视频</a><br><code>{escape(str(video_local.resolve()))}</code></dd>
            <dt>完成时间</dt><dd>{escape(item['completed_at'] or '')}</dd>
          </dl>
        </article>""")
    generated = now()
    empty = '<p class="empty">目前还没有生成成功的视频。</p>' if not cards else ""
    document = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>数字人视频问答索引</title>
<style>body{{margin:0;background:#f2f6fa;color:#172536;font:15px/1.65 system-ui,"Microsoft YaHei",sans-serif}}header,main{{max-width:1100px;margin:auto}}header{{padding:36px 20px 20px}}h1{{margin:0}}header p{{color:#64748b}}main{{padding:0 20px 40px;display:grid;gap:14px}}article{{background:#fff;border:1px solid #dce4ec;border-radius:12px;padding:18px;box-shadow:0 4px 16px #173b5a0b}}.top{{display:flex;justify-content:space-between;color:#1467d8}}h2{{font-size:18px;margin:10px 0}}.answer{{background:#f8fafc;padding:12px;border-radius:8px}}dl{{display:grid;grid-template-columns:90px 1fr;gap:8px;margin:0}}dt{{font-weight:700}}dd{{margin:0;min-width:0}}code{{overflow-wrap:anywhere;color:#475569}}a{{color:#087f78;font-weight:700}}.empty{{background:#fff;padding:30px;border-radius:12px}}@media(max-width:600px){{dl{{grid-template-columns:1fr}}}}</style></head>
<body><header><h1>数字人视频问答索引</h1><p>成功视频 {len(records)} 个 · 生成时间 {escape(generated)}</p></header><main>{empty}{''.join(cards)}</main></body></html>"""
    output = settings.data_dir / "video_catalog.html"
    temp = output.with_suffix(".tmp")
    temp.write_text(document, encoding="utf-8")
    temp.replace(output)
    return output, len(records)
