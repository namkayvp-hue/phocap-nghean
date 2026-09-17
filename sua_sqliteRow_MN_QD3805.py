from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(r"C:\PhoCap\cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py")

text = FILE.read_text(encoding="utf-8")

start = text.find("def school_candidates(")
end = text.find("def resolve_missing_codes(", start)

if start < 0 or end < 0:
    raise RuntimeError("Không xác định được vùng hàm school_candidates().")

block = text[start:end]

old = """        if expected_key == school_key or expected_key == source_key:
            candidates.append(row)
"""

new = """        if expected_key == school_key or expected_key == source_key:
            # resolve_missing_codes() dùng .get(), nên phải trả dict
            # đồng thời giữ khóa tương thích với cấu trúc cũ.
            item = dict(row)
            item["id"] = item.get("school_id")
            item["code"] = item.get("school_code")
            item["name"] = item.get("school_name")
            candidates.append(item)
"""

if old not in block:
    raise RuntimeError(
        "Không tìm thấy đoạn candidates.append(row) cần sửa. "
        "Dừng an toàn, không thay đổi file."
    )

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_sua_sqliteRow_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)

shutil.copy2(FILE, backup)

block = block.replace(old, new, 1)
text = text[:start] + block + text[end:]

FILE.write_text(text, encoding="utf-8")

print("=" * 100)
print("ĐÃ SỬA sqlite3.Row -> dict")
print("File   :", FILE)
print("Backup :", backup)
print("KHÔNG sửa Excel nguồn.")
print("KHÔNG ghi phocap.db.")
print("=" * 100)
