from pathlib import Path
from datetime import datetime
import shutil

FILE = Path(r"C:\PhoCap\cai_dat_MN_QD3805_tach_3_dac_thu_va_khoa_ma_an_toan.py")

text = FILE.read_text(encoding="utf-8")

old = '''        school_key = _school_name_key(row["school_name"])
        source_key = _school_name_key(row["source_name"])

        # Chỉ nhận khớp CHÍNH XÁC sau chuẩn hóa.
        # Không dùng contains và không dùng fuzzy.
        if expected_key == school_key or expected_key == source_key:
            # resolve_missing_codes() dùng .get(), nên phải trả dict
            # đồng thời giữ khóa tương thích với cấu trúc cũ.
            item = dict(row)
            item["id"] = item.get("school_id")
            item["code"] = item.get("school_code")
            item["name"] = item.get("school_name")
            candidates.append(item)
'''

new = '''        school_name_raw = str(row["school_name"] or "").strip()
        commune_name_raw = str(row["commune_name"] or "").strip()

        school_key = _school_name_key(school_name_raw)
        source_key = _school_name_key(row["source_name"])

        # Giữ nguyên cách so khớp đã làm được trước đây.
        matched = (
            expected_key == school_key
            or expected_key == source_key
        )

        # Nhánh phụ an toàn:
        # một số tên trường trong DB có gắn chính tên xã ở cuối,
        # ví dụ:
        #   MN Châu Thái Xã Mường Ham
        # trong khi QĐ3805 ghi:
        #   Mầm non Châu Thái
        #
        # Chỉ bỏ hậu tố khi nó KHỚP ĐÚNG commune_name của chính bản ghi.
        # Không dùng contains/fuzzy và không thay đổi dữ liệu DB.
        if not matched and commune_name_raw:
            if school_name_raw.casefold().endswith(commune_name_raw.casefold()):
                base_name = school_name_raw[:-len(commune_name_raw)].strip(
                    " -–—,;"
                )
                base_key = _school_name_key(base_name)

                if expected_key == base_key:
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
        "Không tìm thấy đúng đoạn school_candidates() cần sửa. "
        "DỪNG AN TOÀN - FILE CHƯA THAY ĐỔI."
    )

backup = FILE.with_name(
    FILE.stem
    + "_backup_truoc_bo_hau_to_xa_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
    + FILE.suffix
)

shutil.copy2(FILE, backup)

text = text.replace(old, new, 1)
FILE.write_text(text, encoding="utf-8")

print("=" * 105)
print("ĐÃ BỔ SUNG NHÁNH SO KHỚP HẬU TỐ ĐỊA BÀN")
print("File   :", FILE)
print("Backup :", backup)
print("=" * 105)
print("GIỮ NGUYÊN logic đã chạy được.")
print("KHÔNG hard-code mã 40420313.")
print("KHÔNG sửa Excel nguồn.")
print("KHÔNG ghi phocap.db.")
