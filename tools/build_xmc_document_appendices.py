"""Extract appendix 4/5 as complete PDF documents, preserving source layout."""
from pathlib import Path
import json
import re
import pymupdf
from app.xmc_appendices import TEMPLATE_DIR


def build():
    folder = Path(__file__).resolve().parents[1] / "Biểu mẫu Xóa mù"
    source = next((folder / name for name in ("Mẫu biểu 1.pdf", "Mấu biểu 1.pdf")
                   if (folder / name).exists()), None)
    if source is None:
        raise FileNotFoundError("Không tìm thấy Mẫu biểu 1.pdf / Mấu biểu 1.pdf")
    with pymupdf.open(source) as doc:
        starts = {}
        for index, page in enumerate(doc):
            for number in (4, 5):
                if f"PHỤ LỤC {number}" in page.get_text():
                    starts[number] = index
        if set(starts) != {4, 5} or starts[4] >= starts[5]:
            raise ValueError("Không xác định được ranh giới phụ lục 4 và 5")
        for number, end in ((4, starts[5] - 1), (5, len(doc) - 1)):
            with pymupdf.open() as output:
                output.insert_pdf(doc, from_page=starts[number], to_page=end)
                output.save(TEMPLATE_DIR / f"Phu_luc_{number}.pdf")
                paragraphs = []
                for page in output:
                    for block in page.get_text('blocks', sort=True):
                        if block[6] != 0:
                            continue
                        for part in re.split(r'\n(?=[+\-] |[IVX]+\.\s|\d+\.\s|[a-z]\)\s)', block[4]):
                            text = ' '.join(part.split())
                            if text:
                                paragraphs.append(text)
                (TEMPLATE_DIR / f"Phu_luc_{number}.json").write_text(
                    json.dumps(paragraphs, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f"Appendix {number}: {len(output)} pages")


if __name__ == "__main__":
    build()
