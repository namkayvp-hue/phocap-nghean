from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(r"C:\PhoCap\cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py")

text = FILE.read_text(encoding="utf-8")

start = text.find("def school_candidates(")
end = text.find("def resolve_missing_codes(", start)

if start < 0:
    raise RuntimeError("Không tìm thấy hàm school_candidates().")

if end < 0:
    raise RuntimeError("Không tìm thấy hàm resolve_missing_codes().")

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_sua_ten_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)

shutil.copy2(FILE, backup)

new_block = r'''def _school_name_key(value):
    """
    Chuẩn hóa tên trường để khóa mã an toàn.

    Ví dụ:
      Mầm non Tiền Phong
      Trường MN Tiền Phong
      Trường MNTiền Phong

    đều trở thành:
      mntienphong

    Chỉ dùng so khớp chính xác sau chuẩn hóa.
    KHÔNG fuzzy.
    """
    import re
    import unicodedata

    s = str(value or "").strip().lower()

    s = unicodedata.normalize("NFD", s)
    s = "".join(
        ch for ch in s
        if unicodedata.category(ch) != "Mn"
    )

    s = s.replace("đ", "d")

    # Bỏ tiền tố "Trường".
    s = re.sub(r"\btruong\b", " ", s)

    # Quy đổi tên cấp học.
    s = re.sub(r"\bmam\s*non\b", "mn", s)

    # Bỏ toàn bộ khoảng trắng / dấu phân cách.
    s = re.sub(r"[^a-z0-9]+", "", s)

    return s


def school_candidates(con, expected_name):
    # Chỉ sử dụng mạng lưới Mầm non năm 2025-2026.
    year = con.execute(
        "SELECT id FROM school_years "
        "WHERE REPLACE(REPLACE(code,'–','-'),'—','-')='2025-2026' "
        "LIMIT 1"
    ).fetchone()

    if year is None:
        raise RuntimeError(
            "Không tìm thấy năm học 2025-2026 trong school_years."
        )

    rows = con.execute(
        """
        SELECT
            s.id AS school_id,
            s.code AS school_code,
            s.name AS school_name,
            c.name AS commune_name,
            sny.source_name
        FROM school_network_year_data sny
        JOIN schools s
            ON s.id = sny.school_id
        LEFT JOIN communes c
            ON c.id = s.commune_id
        WHERE sny.school_year_id = ?
          AND UPPER(TRIM(sny.level_code)) = 'MN'
          AND COALESCE(TRIM(s.code),'') <> ''
        ORDER BY s.id
        """,
        (int(year["id"]),),
    ).fetchall()

    expected_key = _school_name_key(expected_name)

    if not expected_key:
        return []

    candidates = []

    for row in rows:
        school_key = _school_name_key(row["school_name"])
        source_key = _school_name_key(row["source_name"])

        # Chỉ nhận khớp CHÍNH XÁC sau chuẩn hóa.
        # Không dùng contains và không dùng fuzzy.
        if expected_key == school_key or expected_key == source_key:
            candidates.append(row)

    return candidates


'''

new_text = text[:start] + new_block + text[end:]

FILE.write_text(new_text, encoding="utf-8")

print("=" * 100)
print("ĐÃ SỬA HÀM school_candidates()")
print("File :", FILE)
print("Backup:", backup)
print("=" * 100)
print("KHÔNG sửa Excel.")
print("KHÔNG ghi phocap.db.")
