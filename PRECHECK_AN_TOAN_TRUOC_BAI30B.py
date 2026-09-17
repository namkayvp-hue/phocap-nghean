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
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "PRECHECK_AN_TOAN_TRUOC_BAI30B.txt"
JSON_OUT = EXPORTS / "PRECHECK_AN_TOAN_TRUOC_BAI30B.json"

SURVEYS = APP / "routers" / "surveys.py"
TEMPLATES = APP / "templates"

TARGET_TEXT = "Bạn chỉ có quyền xem trạng thái này."
NEW_ROUTE_FRAGMENT = "/phieu/xac-nhan-xa"

CRITICAL_FILES = [
    APP / "routers" / "surveys.py",
    APP / "routers" / "survey_school_workflow.py",
    APP / "routers" / "student_survey_comparison.py",
    APP / "pcgd_mn_report_builders_v1.py",
    APP / "routers" / "mn_official_reports.py",
    APP / "working_school_year.py",
    APP / "access_control.py",
    APP / "main.py",
]

SEARCH_PATTERNS = [
    "commune_confirmed_at",
    "household_confirmed_at",
    "missing_commune_confirmation",
    "Xã/phường đã xác nhận",
    "xac-nhan-xa",
    "xac_nhan_xa",
    "commune_confirm",
    "confirm_commune",
]


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


def db_health():
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        row19 = con.execute(
            """
            SELECT
                id,
                survey_batch_id,
                household_id,
                status,
                household_confirmed_at,
                commune_confirmed_at
            FROM survey_forms
            WHERE survey_batch_id=114
              AND household_id=19
            LIMIT 1
            """
        ).fetchone()

        batch114 = con.execute(
            """
            SELECT
                id, commune_id, status, is_locked,
                locked_at, lock_reason
            FROM survey_batches
            WHERE id=114
            LIMIT 1
            """
        ).fetchone()

        state114 = None
        try:
            state114 = con.execute(
                """
                SELECT
                    survey_batch_id,
                    is_commune_locked,
                    commune_locked_at,
                    commune_lock_reason
                FROM survey_commune_execution_states
                WHERE survey_batch_id=114
                LIMIT 1
                """
            ).fetchone()
        except Exception:
            state114 = None
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )

    return integrity, len(fk), row19, batch114, state114


def source_files():
    allowed = {".py", ".html", ".htm", ".jinja", ".j2", ".js"}
    for p in APP.rglob("*"):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts:
            continue
        if p.suffix.lower() not in allowed:
            continue
        yield p


def find_template_hits():
    hits = []
    for p in TEMPLATES.rglob("*.html"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        count = text.count(TARGET_TEXT)
        if count:
            hits.append(
                {
                    "file": str(p.relative_to(ROOT)),
                    "count": count,
                    "sha256": sha256_file(p),
                }
            )
    return hits


def route_conflicts():
    out = []
    for p in APP.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if NEW_ROUTE_FRAGMENT in text:
            for i, line in enumerate(text.splitlines(), start=1):
                if NEW_ROUTE_FRAGMENT in line:
                    out.append(
                        {
                            "file": str(p.relative_to(ROOT)),
                            "line": i,
                            "text": line.strip(),
                        }
                    )
    return out


def search_existing_confirmation_logic():
    results = []
    for p in source_files():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lines = text.splitlines()
        low = text.lower()

        for pattern in SEARCH_PATTERNS:
            pat_low = pattern.lower()
            start = 0
            per_pattern = 0
            while True:
                idx = low.find(pat_low, start)
                if idx < 0:
                    break
                line_no = text.count("\n", 0, idx) + 1
                a = max(1, line_no - 5)
                b = min(len(lines), line_no + 9)
                ctx = "\n".join(
                    f"{n:05d}: {lines[n-1]}"
                    for n in range(a, b + 1)
                )
                results.append(
                    {
                        "pattern": pattern,
                        "file": str(p.relative_to(ROOT)),
                        "line": line_no,
                        "context": ctx,
                    }
                )
                per_pattern += 1
                start = idx + max(1, len(pattern))
                if per_pattern >= 20:
                    break
    return results


def critical_hashes():
    result = {}
    for p in CRITICAL_FILES:
        key = str(p.relative_to(ROOT))
        if p.exists():
            result[key] = sha256_file(p)
        else:
            result[key] = None
    return result


def surveys_prerequisites():
    if not SURVEYS.exists():
        return {
            "exists": False,
            "missing": ["surveys.py"],
        }

    text = SURVEYS.read_text(encoding="utf-8", errors="ignore")
    required = {
        "router": "router",
        "Depends": "Depends",
        "get_db": "get_db",
        "Request": "Request",
        "lay_thong_tin_nguoi_dung": "lay_thong_tin_nguoi_dung",
    }

    missing = [
        name for name, token in required.items()
        if token not in text
    ]

    return {
        "exists": True,
        "missing": missing,
        "route_30b_already_present": NEW_ROUTE_FRAGMENT in text,
        "sha256": sha256_file(SURVEYS),
    }


def assess(
    template_hits,
    conflicts,
    prereq,
    row19,
    batch114,
    state114,
):
    blockers = []
    warnings = []

    if len(template_hits) != 1:
        blockers.append(
            "Không xác định duy nhất template cần sửa "
            f"(tìm thấy {len(template_hits)})."
        )
    elif template_hits[0]["count"] != 1:
        blockers.append(
            "Câu read-only không xuất hiện đúng 1 lần trong template."
        )

    if conflicts:
        blockers.append(
            "Đã tồn tại route chứa '/phieu/xac-nhan-xa'; "
            "không được cài chồng."
        )

    if not prereq["exists"] or prereq["missing"]:
        blockers.append(
            "surveys.py thiếu prerequisite: "
            + repr(prereq.get("missing"))
        )

    if row19 is None:
        warnings.append(
            "Không tìm thấy phiếu batch 114 / household 19; "
            "có thể dữ liệu test đã thay đổi."
        )
    else:
        status = str(row19[3] or "").strip().upper()
        if status != "DA_HOAN_THANH":
            warnings.append(
                f"Phiếu 19 hiện status={status!r}, không phải DA_HOAN_THANH."
            )
        if row19[4] is None:
            warnings.append(
                "Phiếu 19 chưa có household_confirmed_at."
            )
        if row19[5] is not None:
            warnings.append(
                "Phiếu 19 đã có commune_confirmed_at; "
                "không còn cần dùng phiếu này để test nút xác nhận."
            )

    if batch114 is not None:
        if int(batch114[3] or 0) == 1:
            warnings.append("Đợt 114 đang bị khóa.")
    if state114 is not None:
        if int(state114[1] or 0) == 1:
            warnings.append("Xã của đợt 114 đang bị khóa.")

    return blockers, warnings


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 180)
        log(f, "PRECHECK AN TOÀN TRƯỚC BÀI 30B")
        log(f, "MỤC TIÊU: TUYỆT ĐỐI KHÔNG ĐỤNG NGHIỆP VỤ ĐÃ HOÀN THÀNH")
        log(f, "CHỈ ĐỌC SOURCE + DATABASE - KHÔNG GHI SOURCE - KHÔNG GHI DB")
        log(f, "=" * 180)

        for p in (APP, DB):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        db_sha_before = sha256_file(DB)
        integrity, fk_count, row19, batch114, state114 = db_health()

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(f, "FORM_114_19 =", row19)
        log(f, "BATCH_114 =", batch114)
        log(f, "COMMUNE_STATE_114 =", state114)

        hashes = critical_hashes()
        template_hits = find_template_hits()
        conflicts = route_conflicts()
        prereq = surveys_prerequisites()
        existing_logic = search_existing_confirmation_logic()

        log(f, "")
        log(f, "=" * 180)
        log(f, "I. HASH CÁC FILE NGHIỆP VỤ QUAN TRỌNG")
        log(f, "=" * 180)
        for k, v in hashes.items():
            log(f, k, "=", v)

        log(f, "")
        log(f, "=" * 180)
        log(f, "II. TEMPLATE MỤC XÁC NHẬN XÃ")
        log(f, "=" * 180)
        log(f, json.dumps(template_hits, ensure_ascii=False, indent=2))

        log(f, "")
        log(f, "=" * 180)
        log(f, "III. KIỂM TRA TRÙNG ROUTE 30B")
        log(f, "=" * 180)
        log(f, json.dumps(conflicts, ensure_ascii=False, indent=2))

        log(f, "")
        log(f, "=" * 180)
        log(f, "IV. PREREQUISITE surveys.py")
        log(f, "=" * 180)
        log(f, json.dumps(prereq, ensure_ascii=False, indent=2))

        log(f, "")
        log(f, "=" * 180)
        log(f, "V. LOGIC XÁC NHẬN XÃ ĐÃ CÓ TRONG SOURCE")
        log(f, "=" * 180)
        log(f, "EXISTING_LOGIC_HIT_COUNT =", len(existing_logic))
        for item in existing_logic[:160]:
            log(
                f,
                f"--- {item['pattern']} | "
                f"{item['file']}:{item['line']}"
            )
            log(f, item["context"])

        blockers, warnings = assess(
            template_hits,
            conflicts,
            prereq,
            row19,
            batch114,
            state114,
        )

        log(f, "")
        log(f, "=" * 180)
        log(f, "VI. KẾT LUẬN AN TOÀN")
        log(f, "=" * 180)
        log(f, "BLOCKER_COUNT =", len(blockers))
        for x in blockers:
            log(f, "BLOCKER =", x)

        log(f, "WARNING_COUNT =", len(warnings))
        for x in warnings:
            log(f, "WARNING =", x)

        safe = (
            len(blockers) == 0
            and len(template_hits) == 1
            and template_hits[0]["count"] == 1
            and not conflicts
            and not prereq["missing"]
        )

        log(f, "SAFE_TO_PREPARE_30B =", "YES" if safe else "NO")

        db_sha_after = sha256_file(DB)
        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "SOURCE_WRITES_THIS_RUN = 0")
        log(f, "PRECHECK30B_SUCCESS = YES")
        log(f, "=" * 180)

        JSON_OUT.write_text(
            json.dumps(
                {
                    "db_sha": db_sha_before,
                    "integrity": integrity,
                    "fk_count": fk_count,
                    "form_114_19": row19,
                    "batch_114": batch114,
                    "commune_state_114": state114,
                    "critical_hashes": hashes,
                    "template_hits": template_hits,
                    "route_conflicts": conflicts,
                    "surveys_prerequisites": prereq,
                    "existing_confirmation_logic": existing_logic,
                    "blockers": blockers,
                    "warnings": warnings,
                    "safe_to_prepare_30b": safe,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8-sig",
        )

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
                log(f, "PRECHECK30B_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 180)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
