from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(r"C:\PhoCap\cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py")

text = FILE.read_text(encoding="utf-8")

start = text.find("def school_candidates(")
end = text.find("def resolve_missing_codes(", start)

if start < 0 or end < 0:
    raise RuntimeError(
        "Không xác định được hàm school_candidates(). "
        "DỪNG AN TOÀN."
    )

block = text[start:end]

anchor = '''        if matched:
            # resolve_missing_codes() dùng .get(), nên phải trả dict
'''

insert = '''        # Fallback cuối cùng cho lỗi dính chữ trong dữ liệu nguồn:
        #   "Mầm nonThanh Hà"
        # thay vì
        #   "Mầm non Thanh Hà"
        #
        # Chỉ chạy khi toàn bộ quy tắc trước đều KHÔNG khớp.
        # Không fuzzy, không hard-code mã trường.
        if not matched:
            import re

            repaired_name = re.sub(
                r"(?i)(mầm\\s*non)(?=[^\\s])",
                r"\\1 ",
                school_name_raw,
                count=1,
            )

            if repaired_name != school_name_raw:
                repaired_key = _school_name_key(repaired_name)

                if expected_key == repaired_key:
                    matched = True

'''

if anchor not in block:
    raise RuntimeError(
        "Không tìm thấy đúng vị trí cần bổ sung. "
        "DỪNG AN TOÀN - FILE CHƯA THAY ĐỔI."
    )

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_sua_nonThanh_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)

shutil.copy2(FILE, backup)

block = block.replace(anchor, insert + anchor, 1)
text = text[:start] + block + text[end:]

FILE.write_text(text, encoding="utf-8")

print("=" * 105)
print("ĐÃ BỔ SUNG FALLBACK CHO LỖI DÍNH CHỮ: Mầm nonThanh -> Mầm non Thanh")
print("File   :", FILE)
print("Backup :", backup)
print("=" * 105)
print("GIỮ NGUYÊN toàn bộ các nhánh đã chạy được.")
print("KHÔNG hard-code mã 40428320.")
print("KHÔNG sửa Excel nguồn.")
print("KHÔNG ghi phocap.db.")
