# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
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
MODULE = APP / "routers" / "student_survey_comparison.py"
SURVEYS = APP / "routers" / "surveys.py"
EXPORTS = ROOT / "exports"

OUT = EXPORTS / "KHAO_SAT_HAI_NGUYEN_TAC_DOI_CHIEU_31C1B.txt"
JSON_OUT = EXPORTS / "KHAO_SAT_HAI_NGUYEN_TAC_DOI_CHIEU_31C1B.json"

EXPECTED_DB_SHA = "bceddeb34bbb4c6ae3860c6524f8864c9466d4711ae3b89ef2c267bdaa85e4e5"
EXPECTED_MODULE_SHA = "00cc0474685efb5155007bf1ab4b62f48b8a04d89a15e721354e743404a22a08"

TARGET_BATCH_ID = 114
BASELINE_YEAR_ID = 1
CURRENT_YEAR_ID = 2


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


def source_segment(text: str, start: int, end: int) -> str:
    lines = text.splitlines()
    start = max(1, start)
    end = min(len(lines), end)
    return "\n".join(f"{i:05d}: {lines[i-1]}" for i in range(start, end + 1))


def find_function_by_name(text: str, name: str):
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            return {
                "name": name,
                "start": start,
                "end": end,
                "source": "\n".join(lines[start - 1:end]),
                "numbered": source_segment(text, start, end),
            }
    return None


def find_functions_containing(text: str, needles: list[str]):
    tree = ast.parse(text)
    lines = text.splitlines()
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        block = "\n".join(lines[start - 1:end])
        matched = [needle for needle in needles if needle in block]
        if matched:
            results.append({
                "name": node.name,
                "start": start,
                "end": end,
                "matched": matched,
                "numbered": source_segment(text, start, end),
            })
    return results


def inspect_source():
    module_text = MODULE.read_text(encoding="utf-8-sig")
    surveys_text = SURVEYS.read_text(encoding="utf-8-sig")

    result = {
        "module_sha": sha256_file(MODULE),
        "surveys_sha": sha256_file(SURVEYS),
        "scope_functions": [],
        "survey_filter_definition": None,
        "cross_year_functions": [],
        "grade_tokens": {},
    }

    # Các hàm quan trọng hiện có.
    for name in (
        "_baseline_allowed_school_ids",
        "_load_scope_enrollments",
        "_build_comparison_rows",
        "_scope_label",
    ):
        fn = find_function_by_name(module_text, name)
        if fn:
            result["scope_functions"].append(fn)

    # Tìm hàm nạp dữ liệu điều tra bằng dấu vết form_filters / tao_bo_loc...
    result["scope_functions"].extend(
        find_functions_containing(
            module_text,
            [
                "form_filters",
                "tao_bo_loc_phieu_theo_nguoi_dung",
                "SurveyForm.survey_batch_id == batch.id",
            ],
        )
    )

    # Định nghĩa bộ lọc ở surveys.py.
    result["survey_filter_definition"] = find_function_by_name(
        surveys_text,
        "tao_bo_loc_phieu_theo_nguoi_dung",
    )

    # Tìm các hàm thực sự đánh giá trường/lớp/trạng thái liên năm.
    result["cross_year_functions"] = find_functions_containing(
        module_text,
        [
            "cross_year",
            "_schools_equivalent_across_baseline",
            "SAI_KHAC_TRUONG_LOP",
            "Trường hiện tại khác phạm vi trường của nguồn học sinh năm trước",
        ],
    )

    # Kiểm tra có logic lớp/lên lớp thực sự hay chỉ đọc classroom để hiển thị.
    grade_needles = [
        "class_id",
        "class_name_reported",
        "classroom.name",
        "grade",
        "grade_level",
        "lớp",
        "lop",
        "progress",
        "next_grade",
        "expected_grade",
    ]
    low = module_text.casefold()
    for needle in grade_needles:
        result["grade_tokens"][needle] = low.count(needle.casefold())

    return result


def table_names(con):
    return [
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def cols(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def safe_rows(con, sql, params=()):
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    except Exception as exc:
        return [{"_error": repr(exc), "_sql": sql}]


def inspect_db():
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    con.row_factory = sqlite3.Row
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        tables = table_names(con)

        batch = {}
        if "survey_batches" in tables:
            rows = safe_rows(
                con,
                "SELECT * FROM survey_batches WHERE id=? LIMIT 1",
                (TARGET_BATCH_ID,),
            )
            batch = rows[0] if rows else {}

        # Toàn bộ trường của xã trong đợt 114 để kiểm tra phạm vi.
        schools_in_commune = []
        commune_id = batch.get("commune_id")
        if commune_id is not None and "schools" in tables:
            s_cols = cols(con, "schools")
            wanted = [x for x in ("id", "name", "education_level", "school_level", "commune_id") if x in s_cols]
            if wanted:
                schools_in_commune = safe_rows(
                    con,
                    f'SELECT {", ".join(wanted)} FROM schools '
                    'WHERE commune_id=? ORDER BY name',
                    (commune_id,),
                )

        # Cấu trúc lớp và ví dụ lớp theo năm.
        class_info = {
            "columns": cols(con, "classes") if "classes" in tables else [],
            "samples_baseline": [],
            "samples_current": [],
        }
        if "classes" in tables:
            c = class_info["columns"]
            wanted = [x for x in ("id", "name", "school_id", "school_year_id", "grade_level", "level", "education_level") if x in c]
            if wanted and "school_year_id" in c:
                class_info["samples_baseline"] = safe_rows(
                    con,
                    f'SELECT {", ".join(wanted)} FROM classes '
                    'WHERE school_year_id=? ORDER BY school_id, name LIMIT 120',
                    (BASELINE_YEAR_ID,),
                )
                class_info["samples_current"] = safe_rows(
                    con,
                    f'SELECT {", ".join(wanted)} FROM classes '
                    'WHERE school_year_id=? ORDER BY school_id, name LIMIT 120',
                    (CURRENT_YEAR_ID,),
                )

        # Cấu trúc enrollment để xem có grade_level trực tiếp không.
        enrollment_info = {
            "columns": cols(con, "student_enrollments") if "student_enrollments" in tables else [],
        }

        # Thống kê số phiếu/đối tượng trong đợt để đối chiếu "toàn xã".
        survey_counts = {}
        if "survey_forms" in tables:
            survey_counts["forms_batch"] = con.execute(
                "SELECT COUNT(*) FROM survey_forms WHERE survey_batch_id=?",
                (TARGET_BATCH_ID,),
            ).fetchone()[0]

        if (
            "survey_forms" in tables
            and "survey_people" in tables
        ):
            # Hỗ trợ cả survey_form_id trên survey_people hoặc quan hệ khác.
            sp_cols = cols(con, "survey_people")
            if "survey_form_id" in sp_cols:
                survey_counts["people_batch"] = con.execute(
                    """
                    SELECT COUNT(*)
                    FROM survey_people p
                    JOIN survey_forms f ON f.id=p.survey_form_id
                    WHERE f.survey_batch_id=?
                      AND COALESCE(p.is_active,1)=1
                    """,
                    (TARGET_BATCH_ID,),
                ).fetchone()[0]

        # Nguồn đã khóa cho đợt/năm.
        source_states = []
        if "student_reconciliation_source_states" in tables:
            source_states = safe_rows(
                con,
                """
                SELECT *
                FROM student_reconciliation_source_states
                WHERE target_school_year_id=?
                ORDER BY id
                """,
                (CURRENT_YEAR_ID,),
            )

    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )

    return {
        "integrity": integrity,
        "fk_count": len(fk),
        "batch_114": batch,
        "schools_in_batch_commune": schools_in_commune,
        "class_info": class_info,
        "enrollment_info": enrollment_info,
        "survey_counts": survey_counts,
        "source_states": source_states,
    }


def analyze_scope(source_info):
    text = "\n".join(
        item.get("source", "")
        for item in source_info["scope_functions"]
    )

    uses_form_filter = (
        "tao_bo_loc_phieu_theo_nguoi_dung" in text
        or "form_filters" in text
    )

    survey_filter = source_info.get("survey_filter_definition") or {}
    survey_filter_text = survey_filter.get("source", "")

    restricts_school_or_user = any(
        token in survey_filter_text
        for token in (
            "school_id",
            "assigned_school_id",
            "assigned_teacher_id",
            "teacher_id",
            "SurveyForm.",
        )
    )

    return {
        "comparison_uses_user_form_filter": uses_form_filter,
        "underlying_filter_has_scope_restriction_tokens": restricts_school_or_user,
        "needs_patch_for_school_vs_full_commune": (
            uses_form_filter and restricts_school_or_user
        ),
    }


def analyze_progression(source_info):
    joined = "\n".join(
        item.get("source", "")
        for item in source_info["cross_year_functions"]
    ).casefold()

    has_cross_year = "cross_year" in joined
    has_school_equivalence = "_schools_equivalent_across_baseline" in joined
    has_explicit_grade_progression = any(
        token in joined
        for token in (
            "next_grade",
            "expected_grade",
            "grade_level + 1",
            "grade_level+1",
            "lớp 5",
            "lớp 6",
            "lop 5",
            "lop 6",
            "chuyển cấp",
            "chuyen cap",
        )
    )

    return {
        "cross_year_logic_exists": has_cross_year,
        "school_merger_equivalence_exists": has_school_equivalence,
        "explicit_grade_progression_exists": has_explicit_grade_progression,
        "needs_grade_progression_patch": (
            has_cross_year and not has_explicit_grade_progression
        ),
    }


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 190)
        log(f, "BÀI 31C1B - KHẢO SÁT 2 NGUYÊN TẮC TRƯỚC KHI MỞ XỬ LÝ ĐỐI CHIẾU CHO TRƯỜNG")
        log(f, "1) TRƯỜNG PHẢI ĐỐI CHIẾU HỌC SINH CỦA MÌNH VỚI DỮ LIỆU ĐIỀU TRA TOÀN XÃ LIÊN QUAN")
        log(f, "2) SO SÁNH LIÊN NĂM PHẢI HIỂU LÊN LỚP / CHUYỂN CẤP, KHÔNG SO TRƯỜNG-LỚP MÁY MÓC")
        log(f, "CHỈ ĐỌC SOURCE + DATABASE - KHÔNG SỬA SOURCE - KHÔNG GHI DB")
        log(f, "=" * 190)

        for p in (DB, MODULE, SURVEYS):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        db_sha_before = sha256_file(DB)
        module_sha = sha256_file(MODULE)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "MODULE_SHA =", module_sha)

        if db_sha_before != EXPECTED_DB_SHA:
            raise RuntimeError(
                "DB không còn đúng nền Bài 31C1A. Dừng để tránh kết luận trên nền khác."
            )
        if module_sha != EXPECTED_MODULE_SHA:
            raise RuntimeError(
                "student_survey_comparison.py không còn đúng nền Bài 31C1A."
            )

        source_info = inspect_source()
        db_info = inspect_db()
        scope_result = analyze_scope(source_info)
        progression_result = analyze_progression(source_info)

        log(f, "INTEGRITY =", db_info["integrity"])
        log(f, "FK_COUNT =", db_info["fk_count"])

        log(f, "")
        log(f, "=" * 190)
        log(f, "I. PHẠM VI DỮ LIỆU ĐIỀU TRA CẤP TRƯỜNG")
        log(f, "=" * 190)

        for item in source_info["scope_functions"]:
            log(f, f"--- FUNCTION {item.get('name')} lines {item.get('start')}-{item.get('end')}")
            log(f, item.get("numbered", ""))

        log(f, "")
        log(f, "--- DEFINITION tao_bo_loc_phieu_theo_nguoi_dung")
        if source_info["survey_filter_definition"]:
            log(f, source_info["survey_filter_definition"]["numbered"])
        else:
            log(f, "NOT_FOUND")

        log(f, "SCOPE_ANALYSIS =", json.dumps(
            scope_result, ensure_ascii=False, indent=2
        ))

        log(f, "")
        log(f, "=" * 190)
        log(f, "II. LOGIC LIÊN NĂM / LÊN LỚP / CHUYỂN CẤP")
        log(f, "=" * 190)

        for item in source_info["cross_year_functions"]:
            log(f, f"--- FUNCTION {item.get('name')} lines {item.get('start')}-{item.get('end')}")
            log(f, "MATCHED =", item.get("matched"))
            log(f, item.get("numbered", ""))

        log(f, "GRADE_TOKEN_COUNTS =", json.dumps(
            source_info["grade_tokens"], ensure_ascii=False, indent=2
        ))
        log(f, "PROGRESSION_ANALYSIS =", json.dumps(
            progression_result, ensure_ascii=False, indent=2
        ))

        log(f, "")
        log(f, "=" * 190)
        log(f, "III. DB PHỤC VỤ XÂY QUY TẮC LIÊN NĂM")
        log(f, "=" * 190)
        log(f, "BATCH_114 =", json.dumps(
            db_info["batch_114"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "SCHOOLS_IN_BATCH_COMMUNE =", json.dumps(
            db_info["schools_in_batch_commune"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "CLASS_COLUMNS =", json.dumps(
            db_info["class_info"]["columns"], ensure_ascii=False
        ))
        log(f, "ENROLLMENT_COLUMNS =", json.dumps(
            db_info["enrollment_info"]["columns"], ensure_ascii=False
        ))
        log(f, "BASELINE_CLASS_SAMPLES =", json.dumps(
            db_info["class_info"]["samples_baseline"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "CURRENT_CLASS_SAMPLES =", json.dumps(
            db_info["class_info"]["samples_current"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "SURVEY_COUNTS =", json.dumps(
            db_info["survey_counts"], ensure_ascii=False, indent=2, default=str
        ))
        log(f, "SOURCE_STATES =", json.dumps(
            db_info["source_states"], ensure_ascii=False, indent=2, default=str
        ))

        log(f, "")
        log(f, "=" * 190)
        log(f, "IV. KẾT LUẬN 31C1B")
        log(f, "=" * 190)

        log(
            f,
            "SCHOOL_COMPARISON_CURRENTLY_USES_USER_FORM_SCOPE =",
            "YES" if scope_result["comparison_uses_user_form_filter"] else "NO",
        )
        log(
            f,
            "SCHOOL_NEEDS_FULL_COMMUNE_SURVEY_SCOPE_PATCH =",
            "YES" if scope_result["needs_patch_for_school_vs_full_commune"] else "NO",
        )
        log(
            f,
            "CROSS_YEAR_LOGIC_EXISTS =",
            "YES" if progression_result["cross_year_logic_exists"] else "NO",
        )
        log(
            f,
            "MERGER_SCHOOL_EQUIVALENCE_EXISTS =",
            "YES" if progression_result["school_merger_equivalence_exists"] else "NO",
        )
        log(
            f,
            "GRADE_PROGRESSION_LOGIC_EXISTS =",
            "YES" if progression_result["explicit_grade_progression_exists"] else "NO",
        )
        log(
            f,
            "GRADE_PROGRESSION_PATCH_NEEDED =",
            "YES" if progression_result["needs_grade_progression_patch"] else "NO",
        )

        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "SOURCE_WRITES_THIS_RUN = 0")
        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "AUDIT31C1B_SUCCESS = YES")
        log(f, "=" * 190)

        JSON_OUT.write_text(
            json.dumps(
                {
                    "db_sha": db_sha_before,
                    "source_info": source_info,
                    "scope_result": scope_result,
                    "progression_result": progression_result,
                    "db_info": db_info,
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
        raise SystemExit(main())
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 190)
                log(f, "AUDIT31C1B_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 190)
        except Exception:
            print("ERROR =", repr(exc))
        raise
