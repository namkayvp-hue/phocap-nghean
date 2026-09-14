from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(r"C:\PhoCap\chan_doan_181_MN_QD3805.py")

text = FILE.read_text(encoding="utf-8")

MARKER = "# RAW_FOCUS_5_MA_MN_QD3805"

if MARKER not in text:
    raise RuntimeError(
        "Không tìm thấy khối RAW. DỪNG AN TOÀN."
    )

before, raw_part = text.split(MARKER, 1)

old = '''print(json.dumps(
    payload,
    ensure_ascii=False,
    default=str
))
'''

new = '''print(json.dumps(
    payload,
    ensure_ascii=True,
    default=str
))
'''

if old not in raw_part:
    raise RuntimeError(
        "Không tìm thấy đúng lệnh xuất JSON của tiến trình con. "
        "DỪNG AN TOÀN - FILE CHƯA THAY ĐỔI."
    )

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_sua_cp1252_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)

shutil.copy2(FILE, backup)

raw_part = raw_part.replace(old, new, 1)
text = before + MARKER + raw_part

FILE.write_text(text, encoding="utf-8")

print("=" * 110)
print("ĐÃ SỬA LỖI CP1252 TRONG BẢN CHẨN ĐOÁN")
print("File   :", FILE)
print("Backup :", backup)
print("=" * 110)
print("Chỉ đổi ensure_ascii=False -> True cho stdout tiến trình con.")
print("FILE CÀI CHÍNH: KHÔNG SỬA.")
print("DATABASE: KHÔNG GHI.")
print("=" * 110)
