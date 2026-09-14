# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

KEYWORDS = [
    "2.4.3",
    "xu hướng",
    "xu huong",
    "đạt chuẩn",
    "dat chuan",
    "đăng ký",
    "dang ky",
    "lộ trình",
    "lo trinh",
    "roadmap",
    "recognition",
    "standard",
]

TEXT_EXTS = {
    ".py", ".html", ".htm", ".txt", ".md", ".json",
    ".js", ".css", ".yaml", ".yml",
}


def safe_read(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            pass
    return ""


def scan_source():
    hits = []
    if not APP.exists():
        return hits

    for path in APP.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            if path.stat().st_size > 3_000_000:
                continue
        except OSError:
            continue

        text = safe_read(path)
        if not text:
            continue

        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            low = line.lower()
            if any(k.lower() in low for k in KEYWORDS):
                hits.append(
                    (
                        str(path.relative_to(PROJECT)),
                        i,
                        line.strip()[:500],
                    )
                )
    return hits


def db_schema():
    if not DB.is_file():
        return [], {}

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        tables = [
            r["name"]
            for r in con.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        schemas = {}
        for name in tables:
            cols = con.execute(
                f'PRAGMA table_info("{name}")'
            ).fetchall()
            schemas[name] = [
                {
                    "name": c["name"],
                    "type": c["type"],
                    "notnull": c["notnull"],
                    "pk": c["pk"],
                }
                for c in cols
            ]
        return tables, schemas
    finally:
        con.close()


def table_count_and_sample(table: str, limit: int = 5):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    try:
        count = con.execute(
            f'SELECT COUNT(*) AS n FROM "{table}"'
        ).fetchone()["n"]
        rows = con.execute(
            f'SELECT * FROM "{table}" LIMIT {int(limit)}'
        ).fetchall()
        return count, [dict(r) for r in rows]
    except Exception as exc:
        return None, [{"ERROR": str(exc)}]
    finally:
        con.close()


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = EXPORTS / f"bao_cao_khao_sat_2_4_3_dashboard_dat_chuan_{stamp}.txt"

    lines = []
    lines.append("=" * 120)
    lines.append("KHẢO SÁT BÀI 13B-11-17 - MỤC 2.4.3 DASHBOARD XU HƯỚNG / LỘ TRÌNH ĐẠT CHUẨN")
    lines.append("=" * 120)
    lines.append(f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}")
    lines.append(f"Dự án: {PROJECT}")
    lines.append(f"Database: {DB}")
    lines.append("")

    # 1. DB health
    lines.append("I. KIỂM TRA DATABASE")
    if DB.is_file():
        con = sqlite3.connect(DB)
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = len(con.execute("PRAGMA foreign_key_check").fetchall())
        finally:
            con.close()
        lines.append(f"integrity_check: {integrity}")
        lines.append(f"foreign_key_check: {fk} lỗi")
    else:
        lines.append("KHÔNG TÌM THẤY DATABASE.")
    lines.append("")

    # 2. source hits
    lines.append("II. DẤU VẾT MỤC 2.4.3 / ĐẠT CHUẨN / LỘ TRÌNH TRONG MÃ NGUỒN")
    hits = scan_source()
    lines.append(f"Tổng số dòng khớp từ khóa: {len(hits)}")
    for rel, lineno, text in hits[:500]:
        lines.append(f"{rel}:{lineno}: {text}")
    if len(hits) > 500:
        lines.append(f"... còn {len(hits) - 500} dòng không in để báo cáo gọn.")
    lines.append("")

    # 3. schema
    lines.append("III. CẤU TRÚC CÁC BẢNG CÓ KHẢ NĂNG LIÊN QUAN")
    tables, schemas = db_schema()
    interesting = []
    for table in tables:
        joined = " ".join(
            [table] + [c["name"] for c in schemas.get(table, [])]
        ).lower()
        if any(
            key in joined
            for key in (
                "commune", "school_year", "survey", "standard",
                "recogn", "roadmap", "target", "plan", "registration",
                "progress", "lock", "report",
            )
        ):
            interesting.append(table)

    lines.append("Các bảng phù hợp từ khóa:")
    for table in interesting:
        lines.append(f"\n[{table}]")
        for c in schemas.get(table, []):
            lines.append(
                f"  - {c['name']} | {c['type']} | "
                f"notnull={c['notnull']} | pk={c['pk']}"
            )

        count, sample = table_count_and_sample(table, 3)
        lines.append(f"  Số bản ghi: {count}")
        for idx, row in enumerate(sample, start=1):
            # Tránh đưa hash mật khẩu ra báo cáo.
            sanitized = {
                k: ("<HIDDEN>" if "password" in k.lower() else v)
                for k, v in row.items()
            }
            lines.append(f"  Mẫu {idx}: {sanitized}")
    lines.append("")

    # 4. specific core tables
    lines.append("IV. KIỂM TRA NHANH DANH MỤC XÃ VÀ NĂM HỌC")
    for table in ("communes", "school_years"):
        if table in tables:
            count, sample = table_count_and_sample(table, 10)
            lines.append(f"[{table}] số bản ghi={count}")
            for row in sample:
                lines.append(str(row))
        else:
            lines.append(f"[{table}] không tồn tại.")
    lines.append("")

    # 5. files/routes most likely
    lines.append("V. FILE/ROUTE NÊN DÙNG CHO BỘ CÀI TIẾP THEO")
    likely = sorted(
        {
            rel
            for rel, _, _ in hits
            if (
                "menu" in rel.lower()
                or "survey" in rel.lower()
                or "progress" in rel.lower()
                or "report" in rel.lower()
                or "dashboard" in rel.lower()
                or "trend" in rel.lower()
            )
        }
    )
    for rel in likely[:100]:
        lines.append(rel)
    lines.append("")

    lines.append("VI. KẾT LUẬN KHẢO SÁT")
    lines.append(
        "Báo cáo này CHỈ ĐỌC mã nguồn và database, KHÔNG sửa bất kỳ file hay dữ liệu nào."
    )
    lines.append(
        "Hãy gửi file báo cáo này cùng BIỂU ĐĂNG KÝ NĂM ĐẠT CHUẨN CỦA CÁC XÃ để thiết kế bộ cài 2.4.3."
    )

    report.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    print("=" * 120)
    print("KHẢO SÁT HOÀN TẤT - KHÔNG THAY ĐỔI MÃ NGUỒN/DATABASE")
    print("=" * 120)
    print(f"Báo cáo: {report}")
    print("Hãy gửi file báo cáo này và biểu đăng ký năm đạt chuẩn của các xã.")


if __name__ == "__main__":
    main()
