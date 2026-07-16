import json
import sys
import time
import urllib.parse
import urllib.request
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.seed import SCENIC_QA


def translate(text: str) -> str:
    query = urllib.parse.urlencode({"client": "gtx", "sl": "zh-CN", "tl": "en", "dt": "t", "q": text})
    request = urllib.request.Request(
        "https://translate.googleapis.com/translate_a/single?" + query,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return "".join(part[0] for part in payload[0] if part[0]).strip()


def main() -> None:
    source = [(spot, question, answer) for spot, items in SCENIC_QA.items() for question, answer in items]

    chunks = [source[index:index + 10] for index in range(0, len(source), 10)]

    def translate_chunk(chunk):
        text = "\n".join(
            f"ZXQ{index:03d}ZX\nQuestion: {question}\nAnswer: {answer}"
            for index, (_, question, answer) in enumerate(chunk)
        )
        for attempt in range(4):
            try:
                result = translate(text)
                blocks = re.split(r"ZXQ\d{3}ZX", result)[1:]
                if len(blocks) != len(chunk):
                    raise ValueError(f"Expected {len(chunk)} translated blocks, got {len(blocks)}")
                translated_items = []
                for (spot, question, _), block in zip(chunk, blocks):
                    match = re.search(r"Question:\s*(.*?)\s*Answer:\s*(.*)", block, re.S | re.I)
                    if not match:
                        raise ValueError("Translated block did not preserve Question/Answer labels")
                    translated_items.append((spot, question, match.group(1).strip(), match.group(2).strip()))
                return translated_items
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    translated = {spot: [] for spot in SCENIC_QA}
    with ThreadPoolExecutor(max_workers=4) as executor:
        for chunk_result in executor.map(translate_chunk, chunks):
            for spot, question, question_en, answer_en in chunk_result:
                translated[spot].append((question, question_en, answer_en))
    output = Path(__file__).resolve().parents[1] / "backend" / "qa_en.py"
    lines = ["# Generated bilingual seed data. Regenerate with tools/generate_qa_en.py.\n", "SCENIC_QA_EN = {"]
    for spot, items in translated.items():
        lines.append(f"    {spot!r}: [")
        lines.extend(f"        ({zh!r}, {en_q!r}, {en_a!r})," for zh, en_q, en_a in items)
        lines.append("    ],")
    lines.append("}\n")
    output.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
