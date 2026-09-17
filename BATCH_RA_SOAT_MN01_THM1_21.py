# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
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
DB = ROOT / "data" / "phocap.db"
APP = ROOT / "app"
EXPORT_DIR = ROOT / "exports"

OUT = EXPORT_DIR / "BATCH_RA_SOAT_MN01_THM1_21.txt"
JSON_OUT = EXPORT_DIR / "BATCH_21_MN01_THM1_SOURCE_AUDIT.json"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

SKIP_DIRS = {
    ".venv", "venv", ".git", "__pycache__", "node_modules",
    "backups", "exports",
}

GROUPS = {
    "MOVEMENT_UI": [
        "Có chuyển đi trong năm học",
        "chuyen_di",
        "chuyển đi",
        "moved_out",
        "move_out",
        "residence",
        "cư trú",
    ],
    "STUDY_LOCATION": [
        "trong tỉnh",
        "ngoài tỉnh",
        "ngoai_tinh",
        "trong_tinh",
        "học nơi khác",
        "hoc_noi_khac",
        "school_location",
        "school_province",
        "tỉnh học",
        "địa bàn khác",
    ],
    "MN01_REPORT": [
        "MN-01-TE",
        "MN_01_TE",
        "MN01",
        "PCGDMN",
        "trẻ ở tỉnh học",
        "địa bàn tỉnh",
        "địa bàn khác",
    ],
    "TH_M1_REPORT": [
        "_th_m1_percent",
        "TH-M1",
        "TH_M1",
        "PCGD_TH_M1",
        "M1 Tiểu học",
        "M1-TH",
    ],
    "PERCENT_FORMAT": [
        "number_format",
        "0\\%",
        "0%",
        "percent",
        "percentage",
        "tỷ lệ",
        "tỉ lệ",
    ],
}

LOG = None


def log(*args):
    s = " ".join(str(x) for x in args)
    print(s)
    if LOG:
        LOG.write(s + "\n")
        LOG.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def table_info(conn, table):
    if not table_exists(conn, table):
        return {"exists": False}
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {
        "exists": True,
        "columns": [
            {
                "cid": r[0],
                "name": r[1],
                "type": r[2],
                "notnull": r[3],
                "default": r[4],
                "pk": r[5],
            }
            for r in rows
        ],
        "count": int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]),
    }


def source_files():
    result = []
    for p in APP.rglob("*"):
        if not p.is_file():
            continue
        if any(part.lower() in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in {".py", ".html", ".jinja2", ".js"}:
            continue
        try:
            if p.stat().st_size > 5 * 1024 * 1024:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        result.append((p, text))
    return result


def line_hits(text, patterns, context=5):
    lines = text.splitlines()
    low_patterns = [p.lower() for p in patterns]
    results = []
    seen = set()

    for i, line in enumerate(lines):
        low = line.lower()
        matched = [patterns[idx] for idx, lp in enumerate(low_patterns) if lp in low]
        if not matched:
            continue

        start = max(0, i - context)
        end = min(len(lines), i + context + 1)
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "line": i + 1,
            "matched": matched,
            "snippet": "\n".join(
                f"{j+1:05d}: {lines[j]}"
                for j in range(start, end)
            ),
        })
    return results


def focused_functions(text, keyword):
    """
    In ra nguyên hàm Python chứa keyword nếu xác định được bằng AST đơn giản.
    Nếu parse lỗi thì bỏ qua, vì phần line_hits vẫn đủ.
    """
    import ast

    try:
        tree = ast.parse(text)
    except Exception:
        return []

    result = []
    key = keyword.lower()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        seg = ast.get_source_segment(text, node) or ""
        if key in seg.lower():
            result.append({
                "function": node.name,
                "source": seg[:12000],
            })
    return result


def main():
    global LOG
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG = OUT.open("w", encoding="utf-8-sig", newline="\n")

    log("=" * 160)
    log("BATCH 21 - RÀ SOÁT MN-01-TE MỤC 15/16 + TH-M1 PHẦN TỶ LỆ %")
    log("CHỈ ĐỌC DATABASE + SOURCE; KHÔNG GHI DỮ LIỆU")
    log("=" * 160)

    db_sha = sha256_file(DB)
    log("DB_SHA =", db_sha)
    log("EXPECTED_DB_SHA =", EXPECTED_DB_SHA)
    if db_sha != EXPECTED_DB_SHA:
        raise RuntimeError("DB SHA khác nền đã chốt sau sáp nhập.")

    conn = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=60,
    )
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        log("INTEGRITY =", integrity)
        log("FK =", len(fk))
        if integrity != "ok" or fk:
            raise RuntimeError("Database health không đạt.")

        db_tables = {
            t: table_info(conn, t)
            for t in (
                "survey_people",
                "survey_person_year_records",
                "survey_forms",
                "households",
                "school_structured_report_inputs",
                "school_network_year_data",
            )
        }

        log("\n" + "=" * 160)
        log("1. CẤU TRÚC DB LIÊN QUAN")
        log("=" * 160)
        for t, info in db_tables.items():
            log(t, "=", json.dumps(info, ensure_ascii=False, default=str))

    finally:
        conn.close()

    files = source_files()
    audit = {
        "db_sha": db_sha,
        "tables": db_tables,
        "groups": {},
        "th_m1_functions": [],
        "mn01_functions": [],
    }

    log("\n" + "=" * 160)
    log("2. SOURCE HITS")
    log("=" * 160)

    for group, patterns in GROUPS.items():
        group_hits = []
        for p, text in files:
            hits = line_hits(text, patterns, context=5)
            if hits:
                group_hits.append({
                    "file": str(p.relative_to(ROOT)),
                    "hits": hits[:80],
                })

        audit["groups"][group] = group_hits

        log("\n---", group, "---")
        log("FILE_HIT_COUNT =", len(group_hits))
        for item in group_hits[:40]:
            log("FILE =", item["file"])
            for hit in item["hits"][:25]:
                log(hit["snippet"])
                log("-" * 100)

    # In nguyên các hàm quan trọng nếu tìm thấy.
    for p, text in files:
        if p.suffix.lower() != ".py":
            continue

        for fn in focused_functions(text, "_th_m1_percent"):
            audit["th_m1_functions"].append({
                "file": str(p.relative_to(ROOT)),
                **fn,
            })

        for keyword in ("MN_01_TE", "MN-01-TE"):
            for fn in focused_functions(text, keyword):
                item = {
                    "file": str(p.relative_to(ROOT)),
                    **fn,
                }
                if item not in audit["mn01_functions"]:
                    audit["mn01_functions"].append(item)

    log("\n" + "=" * 160)
    log("3. HÀM TH-M1 TÌM ĐƯỢC")
    log("=" * 160)
    for item in audit["th_m1_functions"]:
        log("FILE =", item["file"], "FUNCTION =", item["function"])
        log(item["source"])
        log("-" * 120)

    log("\n" + "=" * 160)
    log("4. HÀM MN-01-TE TÌM ĐƯỢC")
    log("=" * 160)
    for item in audit["mn01_functions"][:30]:
        log("FILE =", item["file"], "FUNCTION =", item["function"])
        log(item["source"][:12000])
        log("-" * 120)

    # Kết luận tự động sơ bộ, nhưng không tự sửa.
    movement_cols = []
    info = db_tables.get("survey_person_year_records") or {}
    for c in info.get("columns", []):
        name = str(c["name"])
        low = name.lower()
        if any(k in low for k in ("move", "chuyen", "residen", "school", "province", "location")):
            movement_cols.append(name)

    th_percent_helper_found = bool(audit["th_m1_functions"])
    percent_hits = audit["groups"].get("PERCENT_FORMAT") or []

    summary = {
        "movement_related_columns": movement_cols,
        "th_m1_percent_helper_found": th_percent_helper_found,
        "percent_format_source_files": [x["file"] for x in percent_hits],
        "policy_to_apply_next": {
            "mn01_15_16": (
                "Tách nơi học khác thành TRONG_TINH / NGOAI_TINH; "
                "không trộn với biến động cư trú chuyển đi nếu source hiện tại đang dùng cùng một trường dữ liệu."
            ),
            "th_m1_percent": (
                "Tỷ lệ tự tính bằng Python; không nhập tay; mẫu số 0/thiếu -> để trống; "
                "Excel hiển thị dạng phần trăm có ký hiệu %, không đổi số liệu gốc."
            ),
        },
    }

    audit["summary"] = summary
    JSON_OUT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8-sig",
    )

    log("\n" + "=" * 160)
    log("KẾT LUẬN BATCH 21")
    log("=" * 160)
    log("MOVEMENT_RELATED_COLUMNS =", movement_cols)
    log("TH_M1_PERCENT_HELPER_FOUND =", "YES" if th_percent_helper_found else "NO")
    log("JSON_OUT =", JSON_OUT)
    log("DATABASE_WRITES_THIS_RUN = 0")
    log("DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
    log("BATCH_21_SUCCESS = YES")
    log("NEXT = Dùng kết quả này để tạo Batch 22 sửa đồng thời UI điều tra + MN01 mục 15/16 + TH-M1 tỷ lệ %. Không đoán schema/source.")
    log("=" * 160)

    if LOG:
        LOG.close()
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            log("\n" + "=" * 160)
            log("BATCH_21_SUCCESS = NO")
            log("ERROR =", repr(exc))
            if DB.exists():
                log("DB_SHA_CURRENT =", sha256_file(DB))
            log("DỪNG AN TOÀN.")
            log("=" * 160)
        finally:
            if LOG and not LOG.closed:
                LOG.close()
        rc = 1
    sys.exit(rc)
