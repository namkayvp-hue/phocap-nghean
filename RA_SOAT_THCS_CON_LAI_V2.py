# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
RESOLUTION = ROOT / "data" / "school_merger_registry" / "qd3805_thcs_resolution.json"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "RA_SOAT_THCS_CON_LAI_V2.txt"

# 3 phương án đã hoàn thành chính thức trong các bước vừa chạy.
COMPLETED = {
    "QD3805-OP-0108": "PA2026-C1BD6766C723",  # Mậu Đôn -> Thạch Ngàn
    "QD3805-OP-0210": "PA2026-0104708B7153",  # Thượng Sơn -> Trần Phú
    "QD3805-OP-0644": "PA2026-52415E680B77",  # Yên Hòa -> Yên Thắng
}

# Chỉ là trường đích tiếp nhận thêm điểm/lớp.
# Theo quy tắc mới: GIỮ NGUYÊN, không chạy thuật toán sáp nhập.
KEEP_RECEIVE_ONLY = {
    "QD3805-OP-0486",
    "QD3805-OP-0490",
}

# Có cả gộp trường toàn phần + tiếp nhận thêm điểm/lớp.
# Không được đánh dấu cả operation là GIỮ NGUYÊN.
# Phải tách: phần gộp toàn trường xử lý riêng; phần nhận thêm điểm/lớp = GIỮ NGUYÊN.
MIXED_MERGE_AND_RECEIVE = {
    "QD3805-OP-0126",
    "QD3805-OP-0160",
}

# Nguồn bị tách/chia điểm hoặc phần còn lại sau tách.
# Không dùng engine sáp nhập toàn trường. Cần xử lý nghiệp vụ nguồn riêng.
SPLIT_SOURCE_CASES = {
    "QD3805-OP-0132",
    "QD3805-OP-0133",
    "QD3805-OP-0153",
    "QD3805-OP-0191",
    "QD3805-OP-0489",
}

# Các case còn phải khóa chính xác nguồn/đích hoặc thiếu dữ liệu đối chiếu.
FULL_MERGE_NEEDS_REVIEW = {
    "QD3805-OP-0025",
    "QD3805-OP-0172",
    "QD3805-OP-0203",
}

def load_json(path: Path):
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return json.loads(path.read_text(encoding=enc))
        except Exception:
            pass
    return None

def p(*args):
    print(" ".join(str(x) for x in args))

def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not DB.exists():
        p("DỪNG: không tìm thấy", DB)
        return 2
    if not RESOLUTION.exists():
        p("DỪNG: không tìm thấy", RESOLUTION)
        return 2

    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.execute("PRAGMA query_only=ON")
    try:
        p("=" * 150)
        p("RÀ SOÁT THCS CÒN LẠI V2 - PHÂN LOẠI THEO NGHIỆP VỤ, KHÔNG DÙNG TỪ KHÓA")
        p("CHỈ ĐỌC - KHÔNG GHI DATABASE - KHÔNG SỬA REGISTRY")
        p("=" * 150)

        p("\nDATABASE HEALTH")
        p("integrity =", conn.execute("PRAGMA integrity_check").fetchone()[0])
        p("FK =", len(conn.execute("PRAGMA foreign_key_check").fetchall()))

        p("\n1. KIỂM TRA 3 PHƯƠNG ÁN ĐÃ HOÀN THÀNH")
        for op, plan_id in COMPLETED.items():
            rows = conn.execute(
                """
                SELECT id,plan_id,operation_id,target_school_id,source_school_ids_json,created_at
                FROM school_merger_official_executions
                WHERE plan_id=?
                ORDER BY id
                """,
                (plan_id,),
            ).fetchall()
            p(op, "|", plan_id, "| OFFICIAL_COUNT =", len(rows), "|", rows)

        data = load_json(RESOLUTION)
        if not isinstance(data, dict):
            p("DỪNG: không đọc được resolution JSON")
            return 2

        specials = data.get("special_same_level") or []
        by_op = {
            x.get("operation_id"): x
            for x in specials
            if isinstance(x, dict) and x.get("operation_id")
        }

        def show_group(title, ids, action):
            p("\n" + "=" * 150)
            p(title)
            p("=" * 150)
            for op in sorted(ids):
                x = by_op.get(op)
                p("\nOPERATION =", op)
                if x:
                    p("DISPLAY_TITLE =", x.get("display_title"))
                    p("RELATION_TYPE =", x.get("relation_type"))
                    p("STATUS =", x.get("status"))
                    p("REASON =", x.get("reason"))
                else:
                    p("KHÔNG CÒN TRONG special_same_level hiện tại.")
                p("ACTION =", action)

        show_group(
            "A. ĐÃ HOÀN THÀNH - KHÔNG CHẠY LẠI",
            set(COMPLETED),
            "CLOSED / KHÔNG CHẠY LẠI",
        )

        show_group(
            "B. CHỈ TIẾP NHẬN THÊM ĐIỂM/LỚP -> GIỮ NGUYÊN",
            KEEP_RECEIVE_ONLY,
            "KEEP / GIỮ NGUYÊN; DB_ACTION=NONE; trường tự thêm lớp/GV/HS sau",
        )

        show_group(
            "C. HỖN HỢP: GỘP TRƯỜNG + NHẬN THÊM ĐIỂM/LỚP",
            MIXED_MERGE_AND_RECEIVE,
            "TÁCH NGHIỆP VỤ: phần gộp toàn trường xử lý riêng; phần nhận điểm/lớp = GIỮ NGUYÊN",
        )

        show_group(
            "D. NGUỒN BỊ TÁCH/CHIA ĐIỂM - KHÔNG DÙNG ENGINE GỘP TOÀN TRƯỜNG",
            SPLIT_SOURCE_CASES,
            "RÀ SOÁT NGUỒN RIÊNG; trường đích nhận thêm lớp thì GIỮ NGUYÊN",
        )

        show_group(
            "E. CÒN CẦN KHÓA NGUỒN/ĐÍCH HOẶC DỮ LIỆU",
            FULL_MERGE_NEEDS_REVIEW,
            "KHẢO SÁT TIẾP TRƯỚC KHI QUYẾT ĐỊNH",
        )

        expected = (
            set(COMPLETED)
            | KEEP_RECEIVE_ONLY
            | MIXED_MERGE_AND_RECEIVE
            | SPLIT_SOURCE_CASES
            | FULL_MERGE_NEEDS_REVIEW
        )
        current = set(by_op)
        unclassified = sorted(current - expected)
        missing = sorted(expected - current)

        p("\n" + "=" * 150)
        p("F. ĐỐI CHIẾU")
        p("=" * 150)
        p("SPECIAL_CURRENT_COUNT =", len(current))
        p("CLASSIFIED_CURRENT_COUNT =", len(current & expected))
        p("UNCLASSIFIED =", unclassified)
        p("EXPECTED_NOT_IN_CURRENT_SPECIAL =", missing)

        p("\n" + "=" * 150)
        p("KẾT LUẬN")
        p("=" * 150)
        p("PURE_KEEP_COUNT =", len(KEEP_RECEIVE_ONLY & current))
        p("MIXED_COUNT =", len(MIXED_MERGE_AND_RECEIVE & current))
        p("SPLIT_SOURCE_COUNT =", len(SPLIT_SOURCE_CASES & current))
        p("NEEDS_REVIEW_COUNT =", len(FULL_MERGE_NEEDS_REVIEW & current))
        p("COMPLETED_COUNT =", len(set(COMPLETED) & current))
        p("DATABASE = KHÔNG THAY ĐỔI")
        p("REGISTRY = KHÔNG THAY ĐỔI")
        p("=" * 150)
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    # Ghi đồng thời ra màn hình và file UTF-8.
    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, data):
            for s in self.streams:
                s.write(data)
                s.flush()
        def flush(self):
            for s in self.streams:
                s.flush()

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        old = sys.stdout
        sys.stdout = Tee(old, f)
        try:
            code = main()
        finally:
            sys.stdout = old
    sys.exit(code)
