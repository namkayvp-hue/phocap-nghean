from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(r"C:\PhoCap\cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py")

text = FILE.read_text(encoding="utf-8")

old = '''        if matched:
            # resolve_missing_codes() dùng .get(), nên phải trả dict
            # đồng thời giữ khóa tương thích với cấu trúc cũ.
            item = dict(row)
            item["id"] = item.get("school_id")
            item["code"] = item.get("school_code")
            item["name"] = item.get("school_name")
            candidates.append(item)
'''

new = '''        # Nhánh fallback cuối cùng, không ảnh hưởng các quy tắc trước:
        # QĐ3805 có thể ghi "Mầm non Thanh Đức"
        # trong khi DB lưu "Mầm non Thanh Đức 1".
        #
        # Chỉ bỏ ĐÚNG số 1 ở cuối khóa tên và chỉ sử dụng
        # khi các phép so khớp trước đó đều chưa thành công.
        if not matched:
            if school_key.endswith("1"):
                base_key_without_1 = school_key[:-1]

                if expected_key == base_key_without_1:
                    matched = True

        if matched:
            # resolve_missing_codes() dùng .get(), nên phải trả dict
            # đồng thời giữ khóa tương thích với cấu trúc cũ.
            item = dict(row)
            item["id"] = item.get("school_id")
            item["code"] = item.get("school_code")
            item["name"] = item.get("school_name")
            candidates.append(item)
'''

if old not in text:
    raise RuntimeError(
        "Không tìm thấy đúng vị trí cần bổ sung. "
        "DỪNG AN TOÀN - FILE CHƯA THAY ĐỔI."
    )

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_bo_so_1_cuoi_ten_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)

shutil.copy2(FILE, backup)

text = text.replace(old, new, 1)
FILE.write_text(text, encoding="utf-8")

print("=" * 105)
print("ĐÃ BỔ SUNG FALLBACK: BỎ SỐ 1 CUỐI TÊN KHI SO KHỚP")
print("File   :", FILE)
print("Backup :", backup)
print("=" * 105)
print("GIỮ NGUYÊN toàn bộ logic đã chạy được trước đó.")
print("KHÔNG hard-code mã 40428306.")
print("KHÔNG sửa Excel nguồn.")
print("KHÔNG ghi phocap.db.")
