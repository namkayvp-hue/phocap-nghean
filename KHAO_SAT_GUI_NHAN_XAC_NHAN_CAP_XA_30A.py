# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "KHAO_SAT_GUI_NHAN_XAC_NHAN_CAP_XA_30A.txt"
JSON_OUT = EXPORTS / "KHAO_SAT_GUI_NHAN_XAC_NHAN_CAP_XA_30A.json"

TARGET_BATCH_ID = 114
TARGET_YEAR_ID = 2

SEARCH_TERMS = [
    "Chờ kết luận cấp xã",
    "Chờ kết luận",
    "xác nhận xã",
    "xã/phường xác nhận",
    "gửi xã",
    "gửi báo cáo cho xã",
    "gửi kết quả",
    "nhận kết quả",
    "commune_confirm",
    "commune_confirmation",
    "commune_signoff",
    "signoff",
    "confirmed_by_commune",
    "xa_confirm",
    "xac_nhan_xa",
    "gui_xa",
    "send_to_commune",
]

SCHEMA_KEYWORDS = (
    "confirm", "confirmation", "signoff", "approve", "approval",
    "send", "sent", "receive", "received", "commune", "school",
    "xa_", "xac_nhan", "gui_", "nhan_",
)


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def text_files():
    exts = {".py", ".html", ".htm", ".jinja", ".j2", ".js", ".css"}
    for p in APP.rglob("*"):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts:
            continue
        if p.suffix.lower() not in exts:
            continue
        yield p


def context(text: str, line_no: int, before: int = 6, after: int = 10) -> str:
    lines = text.splitlines()
    a = max(1, line_no - before)
    b = min(len(lines), line_no + after)
    return "\n".join(f"{i:05d}: {lines[i-1]}" for i in range(a, b + 1))


def search_source():
    results = []
    for p in text_files():
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        low = txt.lower()
        for term in SEARCH_TERMS:
            t = term.lower()
            pos = 0
            found = 0
            while True:
                idx = low.find(t, pos)
                if idx < 0:
                    break
                line_no = txt.count("\n", 0, idx) + 1
                results.append({
                    "file": str(p.relative_to(ROOT)),
                    "term": term,
                    "line": line_no,
                    "context": context(txt, line_no),
                })
                found += 1
                pos = idx + max(1, len(t))
                if found >= 12:
                    break
    return results


def table_names(con):
    return [
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def table_columns(con, table):
    return [
        {
            "cid": r[0],
            "name": r[1],
            "type": r[2],
            "notnull": r[3],
            "default": r[4],
            "pk": r[5],
        }
        for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()
    ]


def schema_candidates(con):
    out = []
    for table in table_names(con):
        cols = table_columns(con, table)
        hits = []
        for c in cols:
            name = str(c["name"]).lower()
            if any(k in name for k in SCHEMA_KEYWORDS):
                hits.append(c["name"])
        table_low = table.lower()
        if hits or any(k in table_low for k in SCHEMA_KEYWORDS):
            out.append({
                "table": table,
                "columns": [c["name"] for c in cols],
                "keyword_columns": hits,
            })
    return out


def safe_count(con, table, where="", params=()):
    q = f'SELECT COUNT(*) FROM "{table}"'
    if where:
        q += " WHERE " + where
    try:
        return int(con.execute(q, params).fetchone()[0])
    except Exception:
        return None


def inspect_batch_rows(con):
    report = {}

    tables = set(table_names(con))

    if "survey_batches" in tables:
        cols = [c["name"] for c in table_columns(con, "survey_batches")]
        report["survey_batches_columns"] = cols
        try:
            row = con.execute(
                "SELECT * FROM survey_batches WHERE id=?",
                (TARGET_BATCH_ID,),
            ).fetchone()
            if row is not None:
                report["survey_batch_114"] = dict(zip(cols, row))
        except Exception as exc:
            report["survey_batch_114_error"] = repr(exc)

    if "survey_forms" in tables:
        cols = [c["name"] for c in table_columns(con, "survey_forms")]
        report["survey_forms_columns"] = cols

        batch_col = None
        for cand in ("survey_batch_id", "batch_id"):
            if cand in cols:
                batch_col = cand
                break

        if batch_col:
            report["survey_forms_batch_114_count"] = safe_count(
                con,
                "survey_forms",
                f'"{batch_col}"=?',
                (TARGET_BATCH_ID,),
            )

            interesting = [
                c for c in cols
                if c in {
                    "id", "household_id", "status", "survey_status",
                    "household_confirmed", "commune_confirmed",
                    "school_confirmed", "confirmed_by_commune",
                    "commune_confirmed_at", "school_confirmed_at",
                    "sent_to_commune_at", "received_by_commune_at",
                    "updated_at", "created_at",
                }
                or any(k in c.lower() for k in ("confirm", "signoff", "sent_", "received_"))
            ]
            if interesting:
                q = (
                    "SELECT " + ", ".join(f'"{c}"' for c in interesting)
                    + f' FROM survey_forms WHERE "{batch_col}"=? ORDER BY id LIMIT 100'
                )
                rows = con.execute(q, (TARGET_BATCH_ID,)).fetchall()
                report["survey_forms_batch_114_sample"] = [
                    dict(zip(interesting, r)) for r in rows
                ]

    # Các bảng khác có batch_id/survey_batch_id và cột xác nhận/gửi-nhận.
    related = []
    for table in table_names(con):
        cols = [c["name"] for c in table_columns(con, table)]
        batch_col = next(
            (c for c in ("survey_batch_id", "batch_id") if c in cols),
            None,
        )
        interesting = [
            c for c in cols
            if any(k in c.lower() for k in (
                "confirm", "signoff", "approve", "sent", "receive",
                "commune", "school", "xac_nhan", "gui_", "nhan_",
            ))
        ]
        if batch_col and interesting:
            cnt = safe_count(
                con, table, f'"{batch_col}"=?', (TARGET_BATCH_ID,)
            )
            related.append({
                "table": table,
                "batch_column": batch_col,
                "count_for_batch_114": cnt,
                "interesting_columns": interesting,
            })
    report["related_tables_for_batch_114"] = related

    return report


def inspect_mn02_files():
    hits = []
    tokens = [
        "MN-02", "MN_02", "PCGDMN", "Đạt chuẩn", "Dat chuan",
        "Chờ kết luận cấp xã", "ket_luan", "conclusion",
    ]
    for p in text_files():
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        low = txt.lower()
        if not any(t.lower() in low for t in tokens):
            continue

        for i, line in enumerate(txt.splitlines(), start=1):
            line_low = line.lower()
            if any(t.lower() in line_low for t in tokens):
                hits.append({
                    "file": str(p.relative_to(ROOT)),
                    "line": i,
                    "line_text": line.strip(),
                    "context": context(txt, i, 5, 12),
                })
                if sum(1 for h in hits if h["file"] == str(p.relative_to(ROOT))) >= 20:
                    break
    return hits


def summarize_routes(source_hits):
    route_hits = []
    for item in source_hits:
        ctx = item["context"]
        if "@router." in ctx or "def " in ctx:
            route_hits.append(item)
    return route_hits


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 180)
        log(f, "BÀI 30A - KHẢO SÁT TRƯỜNG/XÃ GỬI-NHẬN KẾT QUẢ VÀ XÁC NHẬN PHIẾU")
        log(f, "MỤC TIÊU: LÀM RÕ NGUYÊN NHÂN MN-02 CỘT 22 ĐANG 'CHỜ KẾT LUẬN CẤP XÃ'")
        log(f, "CHỈ ĐỌC SOURCE + DATABASE. KHÔNG SỬA SOURCE. KHÔNG GHI DATABASE.")
        log(f, "=" * 180)

        if not DB.exists():
            raise RuntimeError(f"Không tìm thấy DB: {DB}")
        if not APP.exists():
            raise RuntimeError(f"Không tìm thấy app: {APP}")

        db_sha = sha256_file(DB)
        wal = DB.with_name(DB.name + "-wal")
        journal = DB.with_name(DB.name + "-journal")

        log(f, "DB_SHA =", db_sha)
        log(f, "WAL_SIZE =", wal.stat().st_size if wal.exists() else 0)
        log(f, "JOURNAL_SIZE =", journal.stat().st_size if journal.exists() else 0)

        con = sqlite3.connect(
            f"file:{DB.as_posix()}?mode=ro",
            uri=True,
            timeout=30,
        )
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            if integrity != "ok" or fk:
                raise RuntimeError(
                    f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
                )

            schema = schema_candidates(con)
            batch = inspect_batch_rows(con)
        finally:
            con.close()

        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", len(fk))
        log(f, "TARGET_BATCH_ID =", TARGET_BATCH_ID)
        log(f, "TARGET_YEAR_ID =", TARGET_YEAR_ID)

        log(f, "")
        log(f, "=" * 180)
        log(f, "I. TÌM CHÍNH XÁC NGUỒN 'CHỜ KẾT LUẬN CẤP XÃ'")
        log(f, "=" * 180)

        source_hits = search_source()
        exact_hits = [
            h for h in source_hits
            if h["term"].lower() == "chờ kết luận cấp xã"
        ]
        log(f, "EXACT_HIT_COUNT =", len(exact_hits))
        for h in exact_hits:
            log(f, f"--- {h['file']}:{h['line']}")
            log(f, h["context"])

        log(f, "")
        log(f, "=" * 180)
        log(f, "II. ROUTE / HÀM CÓ LIÊN QUAN GỬI-NHẬN-XÁC NHẬN")
        log(f, "=" * 180)

        route_hits = summarize_routes(source_hits)
        log(f, "ROUTE_CONTEXT_COUNT =", len(route_hits))
        for h in route_hits[:120]:
            log(f, f"--- TERM={h['term']} | {h['file']}:{h['line']}")
            log(f, h["context"])

        log(f, "")
        log(f, "=" * 180)
        log(f, "III. SCHEMA CÓ DẤU VẾT XÁC NHẬN / GỬI-NHẬN")
        log(f, "=" * 180)
        log(f, "SCHEMA_CANDIDATE_COUNT =", len(schema))
        for item in schema:
            log(
                f,
                f"TABLE={item['table']} | KEYWORD_COLUMNS={item['keyword_columns']}"
            )

        log(f, "")
        log(f, "=" * 180)
        log(f, "IV. DỮ LIỆU ĐỢT 114 - XÃ NGHI LỘC")
        log(f, "=" * 180)
        log(f, json.dumps(batch, ensure_ascii=False, indent=2, default=str))

        log(f, "")
        log(f, "=" * 180)
        log(f, "V. NGUỒN XUẤT MN-02 / ĐẠT CHUẨN")
        log(f, "=" * 180)

        mn02_hits = inspect_mn02_files()
        log(f, "MN02_SOURCE_HIT_COUNT =", len(mn02_hits))
        for h in mn02_hits[:120]:
            log(f, f"--- {h['file']}:{h['line']} | {h['line_text']}")
            log(f, h["context"])

        result = {
            "db_sha": db_sha,
            "integrity": integrity,
            "fk_count": len(fk),
            "target_batch_id": TARGET_BATCH_ID,
            "source_hits": source_hits,
            "exact_waiting_conclusion_hits": exact_hits,
            "route_hits": route_hits,
            "schema_candidates": schema,
            "batch_114": batch,
            "mn02_hits": mn02_hits,
        }
        JSON_OUT.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8-sig",
        )

        log(f, "")
        log(f, "=" * 180)
        log(f, "KẾT LUẬN BÀI 30A")
        log(f, "=" * 180)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "SOURCE_WRITES_THIS_RUN = 0")
        log(f, "DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
        log(f, "JSON_OUT =", JSON_OUT)
        log(f, "AUDIT30A_SUCCESS = YES")
        log(f, "NEXT = Dựa đúng dependency của MN-02 để hoàn thiện luồng Trường -> Xã -> Xác nhận, không sửa các nghiệp vụ đang chạy.")
        log(f, "=" * 180)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 180)
                log(f, "AUDIT30A_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 180)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
