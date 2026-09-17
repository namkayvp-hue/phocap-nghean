from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(
    r"C:\PhoCap\cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py"
)

if not FILE.exists():
    raise SystemExit("Không tìm thấy: " + str(FILE))

text = FILE.read_text(encoding="utf-8")

# Chỉ tìm bên trong khối kiểm chứng mới.
marker = '_verify_code = r"""'

pos = text.find(marker)

if pos < 0:
    raise RuntimeError(
        "Không tìm thấy khối _verify_code. "
        "DỪNG AN TOÀN - KHÔNG SỬA FILE."
    )

start = text.find(
    "year = con.execute(",
    pos,
)

if start < 0:
    raise RuntimeError(
        "Không tìm thấy đoạn lấy năm học trong _verify_code. "
        "DỪNG AN TOÀN."
    )

end_token = ").fetchone()"
end = text.find(
    end_token,
    start,
)

if end < 0:
    raise RuntimeError(
        "Không tìm thấy cuối đoạn con.execute(...).fetchone(). "
        "DỪNG AN TOÀN."
    )

end += len(end_token)

old_block = text[start:end]

new_block = r'''rows_year = con.execute(
    "SELECT id, code FROM school_years"
).fetchall()

year = next(
    (
        r
        for r in rows_year
        if str(r[1] or "")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .strip()
        == "2026-2027"
    ),
    None,
)'''

# Bảo vệ: đoạn bị thay phải thật sự chứa SELECT id cũ.
if "SELECT id" not in old_block:
    raise RuntimeError(
        "Đoạn tìm được không giống lỗi SQL lồng chuỗi đã xác định. "
        "DỪNG AN TOÀN."
    )

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_sua_loi_SQL_long_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)

shutil.copy2(FILE, backup)

text = text[:start] + new_block + text[end:]

FILE.write_text(
    text,
    encoding="utf-8",
)

print("=" * 118)
print("ĐÃ SỬA LỖI CÚ PHÁP SQL LỒNG CHUỖI")
print("File   :", FILE)
print("Backup :", backup)
print("=" * 118)
print("Chỉ sửa đoạn xác định school_year_id=2026-2027.")
print("Không sửa logic sáp nhập.")
print("Không sửa Excel nguồn.")
print("Không ghi phocap.db.")
print("=" * 118)
