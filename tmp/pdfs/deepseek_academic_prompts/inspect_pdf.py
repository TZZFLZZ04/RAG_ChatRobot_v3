from __future__ import annotations

import json
from pathlib import Path

import pdfplumber
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
PDF_PATH = ROOT / "source.pdf"


def extract_pages() -> list[dict[str, object]]:
    pages: list[dict[str, object]] = []
    with pdfplumber.open(PDF_PATH) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            pages.append({"page": index, "text": text})
    return pages


def write_extracted_text(pages: list[dict[str, object]]) -> None:
    (ROOT / "extracted_pages.json").write_text(
        json.dumps(pages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    sections = [
        f"===== PAGE {item['page']} =====\n{item['text']}"
        for item in pages
    ]
    (ROOT / "extracted.txt").write_text("\n\n".join(sections), encoding="utf-8")


def write_contact_sheets() -> int:
    image_paths = sorted(ROOT.glob("page-*.png"))
    for batch_start in range(0, len(image_paths), 10):
        batch = image_paths[batch_start : batch_start + 10]
        thumbnails: list[Image.Image] = []
        for image_path in batch:
            with Image.open(image_path) as image:
                thumbnail = image.convert("RGB")
                thumbnail.thumbnail((480, 680))
                canvas = Image.new("RGB", (500, 720), "white")
                canvas.paste(thumbnail, ((500 - thumbnail.width) // 2, 30))
                ImageDraw.Draw(canvas).text((10, 8), image_path.stem, fill="black")
                thumbnails.append(canvas)

        sheet = Image.new("RGB", (1000, 720 * 5), "#dddddd")
        for index, thumbnail in enumerate(thumbnails):
            sheet.paste(thumbnail, ((index % 2) * 500, (index // 2) * 720))

        first = batch_start + 1
        last = batch_start + len(batch)
        sheet.save(ROOT / f"contact-{first:02d}-{last:02d}.jpg", quality=88)

    return (len(image_paths) + 9) // 10


def main() -> None:
    pages = extract_pages()
    write_extracted_text(pages)
    contact_count = write_contact_sheets()
    character_count = sum(len(str(item["text"])) for item in pages)
    print(f"pages={len(pages)} chars={character_count} contacts={contact_count}")


if __name__ == "__main__":
    main()
