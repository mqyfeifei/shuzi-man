import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path

from .config import settings
from .db import rows


SPOT_FOLDER_NAMES = {"灵山景区": "灵山", "敦煌": "敦煌", "西湖": "西湖"}


def clean_question_for_filename(question: str, max_length: int = 100) -> str:
    text = unicodedata.normalize("NFC", question)
    text = "".join(
        char for char in text
        if not unicodedata.category(char).startswith(("P", "C")) and not char.isspace()
    )
    return (text[:max_length].rstrip(". ") or "未命名问题")


def organized_filename(sequence: int, spot_name: str, question: str, duplicate_index: int = 0) -> str:
    suffix = "" if duplicate_index == 0 else str(duplicate_index)
    return f"{sequence:03d}-{SPOT_FOLDER_NAMES.get(spot_name, spot_name)}-{clean_question_for_filename(question)}{suffix}.mp4"


def organize_final_videos() -> dict:
    settings.final_video_dir.mkdir(parents=True, exist_ok=True)
    records = rows("""SELECT v.id video_id,v.filename,v.relative_path,
      q.id qa_id,q.question,q.answer,q.scenic_spot_id,s.name spot_name,
      (SELECT COUNT(*) FROM qa_items earlier
       WHERE earlier.scenic_spot_id=q.scenic_spot_id AND earlier.id<=q.id) question_sequence
      FROM video_assets v
      JOIN qa_items q ON q.id=v.qa_id
      JOIN scenic_spots s ON s.id=q.scenic_spot_id
      WHERE v.filename IS NOT NULL AND v.relative_path IS NOT NULL
      ORDER BY s.id,q.id,v.id""")
    copied = []
    missing = []
    duplicate_counts = defaultdict(int)
    questions_by_spot = defaultdict(dict)
    known_sources = set()
    for item in records:
        source = settings.data_dir / item["relative_path"]
        known_sources.add(source.resolve())
        if not source.is_file():
            missing.append(item["filename"])
            continue
        folder_name = SPOT_FOLDER_NAMES.get(item["spot_name"], item["spot_name"])
        target_dir = settings.final_video_dir / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        duplicate_index = duplicate_counts[item["qa_id"]]
        duplicate_counts[item["qa_id"]] += 1
        target_name = organized_filename(
            item["question_sequence"], item["spot_name"], item["question"], duplicate_index
        )
        target = target_dir / target_name
        shutil.copy2(source, target)
        copied.append({"source": source.name, "target": str(target.relative_to(settings.data_dir))})
        questions_by_spot[item["spot_name"]][item["qa_id"]] = item

    for spot_name, questions in questions_by_spot.items():
        folder_name = SPOT_FOLDER_NAMES.get(spot_name, spot_name)
        target_dir = settings.final_video_dir / folder_name
        blocks = []
        for item in sorted(questions.values(), key=lambda row: row["question_sequence"]):
            blocks.append(
                f"问题ID：{item['question_sequence']:03d}\n问题：{item['question']}\n答案：{item['answer']}"
            )
        (target_dir / f"{folder_name}问答.txt").write_text("\n\n".join(blocks), encoding="utf-8")

    unmatched = [
        path.name for path in settings.video_dir.glob("*.mp4") if path.resolve() not in known_sources
    ]
    return {
        "copied_count": len(copied),
        "missing_count": len(missing),
        "unmatched_count": len(unmatched),
        "output_dir": str(settings.final_video_dir),
        "folders": sorted(SPOT_FOLDER_NAMES.get(name, name) for name in questions_by_spot),
        "missing_files": missing,
        "unmatched_files": unmatched,
    }
