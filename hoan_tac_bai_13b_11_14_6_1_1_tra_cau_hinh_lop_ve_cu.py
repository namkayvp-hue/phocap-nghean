from __future__ import annotations

import os
import shutil
import sqlite3
import traceback
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

BACKUP = (
    PROJECT
    / "exports"
    / "backup_bai_13b_11_14_6_1_1_20260824_142721"
)

MAIN = PROJECT / "app" / "main.py"
TEMPLATE = (
    PROJECT
    / "app"
    / "templates"
    / "staff"
    / "class_config.html"
)
NEW_ROUTER = (
    PROJECT
    / "app"
    / "routers"
    / "class_structure_inputs.py"
)

DB = PROJECT / "data" / "phocap.db"

BACKUP_MAIN = BACKUP / "app" / "main.py"
BACKUP_TEMPLATE = (
    BACKUP
    / "app"
    / "templates"
    / "staff"
    / "class_config.html"
)
BACKUP_DB = BACKUP / "data" / "phocap.db"


def db_health():
    conn = sqlite3.connect(str(DB))
    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )
        fk = len(
            conn.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )
        counts = {}
        for table in (
            "classes",
            "school_site_year_records",
            "school_class_year_attributes",
            "school_staff_year_summaries",
        ):
            try:
                counts[table] = int(
                    conn.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                )
            except Exception:
                counts[table] = None
        return integrity, fk, counts
    finally:
        conn.close()


def main() -> int:
    print("=" * 118)
    print(
        "HOÀN TÁC BÀI 13B-11.14.6.1.1 - "
        "TRẢ CẤU HÌNH LỚP VỀ TRẠNG THÁI TRƯỚC KHI MỞ RỘNG"
    )
    print("=" * 118)
    print()
    print("MỤC TIÊU:")
    print(
        " - Gỡ phần Trường/Điểm trường/Lớp đơn-Lớp ghép "
        "đã thêm nhầm vào phân hệ Đội ngũ."
    )
    print(
        " - Khôi phục app/main.py và staff/class_config.html "
        "từ backup trước Bài 14.6.1.1."
    )
    print(
        " - Xóa router class_structure_inputs.py "
        "nếu router này do Bài 14.6.1.1 tạo."
    )
    print(
        " - KHÔNG khôi phục database vì Bài 14.6.1.1 "
        "đã xác nhận không thay đổi dữ liệu khi cài."
    )
    print()

    for path in (
        BACKUP,
        BACKUP_MAIN,
        BACKUP_TEMPLATE,
        DB,
    ):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy: {path}"
            )

    integrity_before, fk_before, counts_before = db_health()

    print("integrity_check trước hoàn tác:", integrity_before)
    print("foreign_key_check trước hoàn tác:", fk_before, "lỗi")

    if integrity_before.lower() != "ok" or fk_before != 0:
        raise RuntimeError(
            "Database không đạt kiểm tra an toàn trước hoàn tác."
        )

    print()
    print("Đang khôi phục source/template...")

    shutil.copy2(
        BACKUP_MAIN,
        MAIN,
    )
    print(" - Đã khôi phục app/main.py")

    shutil.copy2(
        BACKUP_TEMPLATE,
        TEMPLATE,
    )
    print(
        " - Đã khôi phục app/templates/staff/class_config.html"
    )

    # Router mới không tồn tại trước bài cài nên không có backup.
    # Chỉ xóa khi có đúng marker/code của Bài 14.6.1.
    if NEW_ROUTER.exists():
        text = NEW_ROUTER.read_text(
            encoding="utf-8-sig",
            errors="ignore",
        )

        if (
            "/doi-ngu/cau-hinh-lop-chi-tiet" in text
            and "school_site_year_records" in text
            and "school_class_year_attributes" in text
        ):
            NEW_ROUTER.unlink()
            print(
                " - Đã xóa app/routers/class_structure_inputs.py"
            )
        else:
            raise RuntimeError(
                "class_structure_inputs.py tồn tại nhưng không khớp "
                "router do Bài 14.6.1.1 tạo; dừng để tránh xóa nhầm."
            )

    integrity_after, fk_after, counts_after = db_health()

    if counts_after != counts_before:
        raise RuntimeError(
            "Số bản ghi database thay đổi trong quá trình hoàn tác."
        )

    if integrity_after.lower() != "ok":
        raise RuntimeError(
            f"integrity_check sau hoàn tác: {integrity_after}"
        )

    if fk_after != 0:
        raise RuntimeError(
            f"foreign_key_check sau hoàn tác: {fk_after} lỗi"
        )

    print()
    print("KIỂM TRA SAU HOÀN TÁC:")
    print(" - app/main.py: ĐÃ KHÔI PHỤC")
    print(" - staff/class_config.html: ĐÃ KHÔI PHỤC")
    print(" - router 14.6.1.1: ĐÃ GỠ")
    print(" - Database: GIỮ NGUYÊN")
    print(" - integrity_check: OK")
    print(" - foreign_key_check: 0 lỗi")
    print()
    print("=" * 118)
    print(
        "HOÀN TÁC BÀI 13B-11.14.6.1.1 THÀNH CÔNG"
    )
    print("=" * 118)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        print()
        print(
            "HOÀN TÁC GẶP LỖI. "
            "Không tự ý khôi phục database."
        )
        raise
