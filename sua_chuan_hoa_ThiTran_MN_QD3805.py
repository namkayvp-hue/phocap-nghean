from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(r"C:\PhoCap\cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py")

text = FILE.read_text(encoding="utf-8")

old = '''    # Quy đổi tên cấp học.
    s = re.sub(r"\\bmam\\s*non\\b", "mn", s)

    # Bỏ toàn bộ khoảng trắng / dấu phân cách.
'''

new = '''    # Quy đổi tên cấp học.
    s = re.sub(r"\\bmam\\s*non\\b", "mn", s)

    # Quy đổi đơn vị hành chính thường gặp trong tên trường:
    # "Thị trấn" <-> "TT"
    # Ví dụ:
    #   MN Thị trấn Mường Xén
    #   Trường Mầm non TT Mường Xén
    # đều về cùng một khóa.
    s = re.sub(r"\\bthi\\s*tran\\b", "tt", s)

    # Bỏ toàn bộ khoảng trắng / dấu phân cách.
'''

if old not in text:
    raise RuntimeError(
        "Không tìm thấy đúng đoạn _school_name_key() cần sửa. "
        "Dừng an toàn, file chưa thay đổi."
    )

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_them_TT_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)

shutil.copy2(FILE, backup)

text = text.replace(old, new, 1)
FILE.write_text(text, encoding="utf-8")

print("=" * 100)
print("ĐÃ BỔ SUNG QUY TẮC: THỊ TRẤN -> TT")
print("File   :", FILE)
print("Backup :", backup)
print("=" * 100)
print("KHÔNG sửa Excel nguồn.")
print("KHÔNG ghi phocap.db.")
