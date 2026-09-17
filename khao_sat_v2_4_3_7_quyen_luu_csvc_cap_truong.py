# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import re
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
EXPORTS = ROOT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT = EXPORTS / f"bao_cao_khao_sat_v2_4_3_7_quyen_luu_csvc_cap_truong_{STAMP}.txt"

TARGET_USERNAME = "truong_40429325"
TARGET_SCHOOL_CODE = "40429325"
TARGET_YEAR = "2026-2027"

SEARCH_ROOTS = [
    APP / "routers",
    APP / "templates",
    APP / "services",
]

KEYWORDS = (
    "csvc",
    "co-so-vat-chat",
    "facility",
    "school_facility",
    "mn01_csvc",
    "school_mn01_csvc_inputs",
    "forbidden",
    "status=forbidden",
    "require_role",
    "role_id",
    "school_id",
)

def add(lines, s=""):
    lines.append(str(s))

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")

def table_exists(con, table: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone())

def columns(con, table: str):
    if not table_exists(con, table):
        return []
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]

def extract_function(lines, node):
    start = max(0, node.lineno - 1)
    end = min(len(lines), getattr(node, "end_lineno", node.lineno))
    return "\n".join(f"{i+1:05d}: {lines[i]}" for i in range(start, end))

def route_info(node):
    rows = []
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Call):
            attr = getattr(dec.func, "attr", None)
            if attr in {"get", "post", "put", "delete", "patch", "api_route"}:
                path = "<dynamic>"
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    path = str(dec.args[0].value)
                rows.append(f"{attr.upper()} {path}")
    return rows

def main():
    lines = []
    add(lines, "=" * 124)
    add(lines, "BÀI 13B-12 V2.4.3.7 - KHẢO SÁT CHỈ ĐỌC QUYỀN/LƯU CSVC CẤP TRƯỜNG")
    add(lines, "=" * 124)
    add(lines, f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}")
    add(lines)
    add(lines, "Mục tiêu:")
    add(lines, "- Xác định vì sao tài khoản trường thấy menu CSVC nhưng khi lưu/chọn chức năng lại về ?status=forbidden.")
    add(lines, "- Xác định route GET/POST thực tế, check quyền, school_id/year_id, bảng lưu và template form.")
    add(lines, "- CHỈ ĐỌC. Không sửa source/database.")
    add(lines)

    if not DB.exists():
        raise FileNotFoundError(DB)

    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        add(lines, "=" * 124)
        add(lines, "I. DATABASE / TÀI KHOẢN TRƯỜNG")
        add(lines, "=" * 124)
        add(lines, f"integrity_check: {con.execute('PRAGMA integrity_check').fetchone()[0]}")
        add(lines, f"foreign_key_check: {len(con.execute('PRAGMA foreign_key_check').fetchall())} lỗi")

        user = con.execute(
            "SELECT * FROM users WHERE username=?",
            (TARGET_USERNAME,)
        ).fetchone()
        add(lines, f"USER {TARGET_USERNAME}: {dict(user) if user else None}")

        school = con.execute(
            "SELECT * FROM schools WHERE code=?",
            (TARGET_SCHOOL_CODE,)
        ).fetchone()
        add(lines, f"SCHOOL {TARGET_SCHOOL_CODE}: {dict(school) if school else None}")

        sy = con.execute(
            "SELECT * FROM school_years WHERE code=?",
            (TARGET_YEAR,)
        ).fetchone()
        add(lines, f"SCHOOL YEAR {TARGET_YEAR}: {dict(sy) if sy else None}")

        add(lines)
        add(lines, "Các bảng CSVC/structured liên quan:")
        for table in (
            "school_mn01_csvc_inputs",
            "school_facility_year_items",
            "school_structured_report_inputs",
            "school_network_year_data",
            "school_site_year_records",
            "school_class_year_attributes",
        ):
            if not table_exists(con, table):
                add(lines, f"- {table}: KHÔNG CÓ")
                continue
            cols = columns(con, table)
            add(lines, f"- {table}: columns={cols}")
            if school and sy and "school_id" in cols and "school_year_id" in cols:
                n = con.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE school_id=? AND school_year_id=?',
                    (school["id"], sy["id"])
                ).fetchone()[0]
                add(lines, f"  current scope count={n}")
                rows = con.execute(
                    f'SELECT * FROM "{table}" WHERE school_id=? ORDER BY id DESC LIMIT 10',
                    (school["id"],)
                ).fetchall()
                for r in rows:
                    add(lines, "  " + repr(dict(r)))

        add(lines)
        add(lines, "=" * 124)
        add(lines, "II. ROUTE / PERMISSION / SAVE CSVC")
        add(lines, "=" * 124)

        seen = set()
        for root in SEARCH_ROOTS:
            if not root.exists():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in {".py", ".html"}:
                    continue
                try:
                    text = read_text(path)
                except Exception:
                    continue

                low = text.lower()
                if not any(k.lower() in low for k in KEYWORDS):
                    continue

                add(lines)
                add(lines, "#" * 124)
                add(lines, f"FILE: {path}")
                add(lines, "-" * 124)

                if path.suffix.lower() == ".py":
                    try:
                        tree = ast.parse(text)
                    except Exception as exc:
                        add(lines, f"AST ERROR: {type(exc).__name__}: {exc}")
                        continue
                    raw = text.splitlines()

                    for node in tree.body:
                        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            continue
                        src = "\n".join(raw[node.lineno-1:getattr(node, "end_lineno", node.lineno)])
                        routes = route_info(node)
                        if routes or any(k.lower() in src.lower() for k in KEYWORDS):
                            if routes or "csvc" in src.lower() or "facility" in src.lower() or "forbidden" in src.lower():
                                add(lines)
                                add(lines, f"FUNCTION: {node.name}")
                                if routes:
                                    add(lines, "ROUTES: " + " | ".join(routes))
                                hits = [k for k in KEYWORDS if k.lower() in src.lower()]
                                add(lines, "KEYWORDS: " + ", ".join(hits))
                                if len(src.splitlines()) <= 260:
                                    add(lines, extract_function(raw, node))
                                else:
                                    add(lines, f"[Hàm dài {len(src.splitlines())} dòng - in vùng từ khóa]")
                                    for i in range(node.lineno-1, getattr(node, "end_lineno", node.lineno)):
                                        if any(k.lower() in raw[i].lower() for k in KEYWORDS):
                                            lo = max(node.lineno-1, i-5)
                                            hi = min(getattr(node, "end_lineno", node.lineno), i+6)
                                            for j in range(lo, hi):
                                                add(lines, f"{j+1:05d}: {raw[j]}")
                else:
                    raw = text.splitlines()
                    hit_idx = []
                    for i, line in enumerate(raw):
                        if any(k.lower() in line.lower() for k in KEYWORDS):
                            hit_idx.append(i)
                    printed = set()
                    for i in hit_idx[:80]:
                        lo = max(0, i-6)
                        hi = min(len(raw), i+7)
                        if (lo, hi) in printed:
                            continue
                        printed.add((lo, hi))
                        add(lines)
                        for j in range(lo, hi):
                            add(lines, f"{j+1:05d}: {raw[j]}")

        add(lines)
        add(lines, "=" * 124)
        add(lines, "III. KẾT LUẬN GỢI Ý TỰ ĐỘNG")
        add(lines, "=" * 124)
        add(lines, "- Nếu GET CSVC cho phép role Trường nhưng POST/save chỉ cho ADMIN/Xã => đây là lỗi phân quyền route.")
        add(lines, "- Nếu POST nhận school_id từ form nhưng tài khoản trường bị cấm chọn school khác => route phải tự khóa school_id theo user.school_id.")
        add(lines, "- Nếu bảng current scope = 0 và POST không commit => cần sửa đúng hàm save, không phải sửa báo cáo.")
        add(lines, "- Sau khi lưu CSVC được, MN-02 mới có thể hoàn thiện các cột Điều kiện bảo đảm/Đạt chuẩn.")
        add(lines, "- Không được kết luận MN-02 'Đạt chuẩn' khi CSVC còn thiếu.")
    finally:
        con.close()

    EXPORTS.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    print("=" * 124)
    print("BÀI 13B-12 V2.4.3.7 - KHẢO SÁT CHỈ ĐỌC QUYỀN/LƯU CSVC CẤP TRƯỜNG")
    print("=" * 124)
    print("ĐÃ TẠO BÁO CÁO:")
    print(REPORT)
    print()
    print("Không có source/database nào bị sửa.")

if __name__ == "__main__":
    main()
