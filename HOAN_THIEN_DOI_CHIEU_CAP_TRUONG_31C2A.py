# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import py_compile
import re
import shutil
import sqlite3
import sys
from datetime import datetime
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

BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "HOAN_THIEN_DOI_CHIEU_CAP_TRUONG_31C2A.txt"

EXPECTED_DB_SHA = "bceddeb34bbb4c6ae3860c6524f8864c9466d4711ae3b89ef2c267bdaa85e4e5"
EXPECTED_MODULE_SHA = "00cc0474685efb5155007bf1ab4b62f48b8a04d89a15e721354e743404a22a08"

OLD_FORM_FILTER = "    form_filters = tao_bo_loc_phieu_theo_nguoi_dung(request)"
NEW_FORM_FILTER = '    # === BAI31C2A_SCHOOL_FULL_COMMUNE_SURVEY_SCOPE_START ===\n    # Đối chiếu cấp TRƯỜNG phải được tìm học sinh của trường trong toàn bộ\n    # dữ liệu điều tra của xã, không chỉ các phiếu do GV của trường được giao.\n    # Các vai trò khác giữ nguyên bộ lọc cũ.\n    _comparison_user = lay_thong_tin_nguoi_dung(request)\n    _comparison_role = normalize_role_code(_comparison_user.get("role_code"))\n    if _comparison_role == SCHOOL_ROLE_CODE:\n        form_filters = []\n    else:\n        form_filters = tao_bo_loc_phieu_theo_nguoi_dung(request)\n    # === BAI31C2A_SCHOOL_FULL_COMMUNE_SURVEY_SCOPE_END ==='

OLD_INDEX_BLOCK = '    indexes = _build_student_indexes(all_students.values())\n    rows: list[dict[str, Any]] = []\n    matched_student_to_row_indexes: dict[int, list[int]] = defaultdict(list)\n\n    for survey_item in survey_rows:\n        form: SurveyForm = survey_item["form"]\n        household: Household = survey_item["household"]\n        person: SurveyPerson = survey_item["person"]\n        record: SurveyPersonYearRecord | None = survey_item["record"]\n\n        candidates, identifier_conflict = _find_candidates(person, indexes)\n'
NEW_INDEX_BLOCK = '    indexes = _build_student_indexes(all_students.values())\n    rows: list[dict[str, Any]] = []\n    matched_student_to_row_indexes: dict[int, list[int]] = defaultdict(list)\n\n    # === BAI31C2A_SCHOOL_RELEVANT_SURVEY_ROWS_START ===\n    # Với tài khoản TRƯỜNG:\n    # - tìm học sinh nguồn của chính trường trong toàn xã;\n    # - chỉ đưa vào bảng các đối tượng khớp nguồn của trường hoặc đang được\n    #   điều tra là học tại chính trường. Không kéo các đối tượng không liên quan.\n    _comparison_user = lay_thong_tin_nguoi_dung(request)\n    _comparison_role = normalize_role_code(_comparison_user.get("role_code"))\n    _current_school_id: int | None = None\n    _current_school_name = ""\n    if _comparison_role == SCHOOL_ROLE_CODE:\n        _raw_school_id = _comparison_user.get("school_id")\n        if _raw_school_id not in (None, ""):\n            try:\n                _current_school_id = int(_raw_school_id)\n            except Exception:\n                _current_school_id = None\n        if _current_school_id is not None:\n            _current_school = db.get(School, _current_school_id)\n            if _current_school is not None:\n                _current_school_name = _normalize_text(_current_school.name)\n    # === BAI31C2A_SCHOOL_RELEVANT_SURVEY_ROWS_END ===\n\n    for survey_item in survey_rows:\n        form: SurveyForm = survey_item["form"]\n        household: Household = survey_item["household"]\n        person: SurveyPerson = survey_item["person"]\n        record: SurveyPersonYearRecord | None = survey_item["record"]\n\n        candidates, identifier_conflict = _find_candidates(person, indexes)\n\n        # === BAI31C2A_SCHOOL_RELEVANCE_FILTER_START ===\n        if _comparison_role == SCHOOL_ROLE_CODE:\n            _survey_points_to_current_school = False\n            if record is not None and _current_school_id is not None:\n                if record.school_id is not None:\n                    _survey_points_to_current_school = (\n                        _effective_school_id_for_year(\n                            int(record.school_id),\n                            int(batch.school_year_id),\n                        )\n                        == _effective_school_id_for_year(\n                            int(_current_school_id),\n                            int(batch.school_year_id),\n                        )\n                    )\n                elif (\n                    _current_school_name\n                    and getattr(record, "school_name_reported", None)\n                ):\n                    _survey_points_to_current_school = (\n                        _normalize_text(record.school_name_reported)\n                        == _current_school_name\n                    )\n\n            if not candidates and not _survey_points_to_current_school:\n                continue\n        # === BAI31C2A_SCHOOL_RELEVANCE_FILTER_END ===\n'

NEW_COMPARE_BLOCK = '# === BAI31C2A_CROSS_YEAR_PROGRESSION_START ===\ndef _class_grade_number_for_cross_year(value: str | None) -> int | None:\n    """\n    Chỉ nhận dạng khối lớp phổ thông rõ ràng: 1..12, ví dụ 5A, Lớp 6A1.\n    Không hiểu \'5 tuổi\' của mầm non là lớp 5.\n    """\n    raw = str(value or "").strip()\n    if not raw:\n        return None\n\n    lowered = raw.casefold()\n    if "tuổi" in lowered or "tuoi" in lowered:\n        return None\n\n    match = re.match(\n        r"^\\s*(?:lớp\\s*)?(1[0-2]|[1-9])(?=[^\\d]|$)",\n        raw,\n        flags=re.IGNORECASE,\n    )\n    if not match:\n        return None\n\n    try:\n        return int(match.group(1))\n    except Exception:\n        return None\n\n\ndef _compare_school_class(\n    record: SurveyPersonYearRecord | None,\n    enrollment: StudentEnrollment | None,\n) -> list[str]:\n    if record is None or enrollment is None:\n        return []\n\n    reasons: list[str] = []\n    cross_year = int(record.school_year_id) != int(enrollment.school_year_id)\n\n    if cross_year:\n        # Nguồn là năm trước, vì vậy thay đổi trường là bình thường khi:\n        # - lên lớp/chuyển cấp;\n        # - chuyển trường;\n        # - trường nguồn đã sáp nhập.\n        # Không coi "khác trường" tự thân là lỗi liên năm.\n        #\n        # Chỉ kiểm tra tiến trình lớp nếu CẢ HAI tên lớp đều nhận dạng chắc chắn\n        # được khối phổ thông 1..12. Nếu tên lớp không chuẩn (đặc biệt mầm non),\n        # không tự suy diễn và không sinh lỗi giả.\n        baseline_class_name = (\n            enrollment.classroom.name\n            if enrollment.classroom is not None\n            else ""\n        )\n        current_class_name = ""\n        if record.classroom is not None:\n            current_class_name = record.classroom.name or ""\n        elif getattr(record, "class_name_reported", None):\n            current_class_name = record.class_name_reported or ""\n\n        baseline_grade = _class_grade_number_for_cross_year(\n            baseline_class_name\n        )\n        current_grade = _class_grade_number_for_cross_year(\n            current_class_name\n        )\n\n        if (\n            baseline_grade is not None\n            and current_grade is not None\n            and baseline_grade < 12\n        ):\n            expected_grade = baseline_grade + 1\n            is_repeating = bool(\n                getattr(record, "is_repeating_grade", False)\n            )\n\n            normal_progression = current_grade == expected_grade\n            repeated_as_recorded = (\n                current_grade == baseline_grade and is_repeating\n            )\n\n            if not normal_progression and not repeated_as_recorded:\n                reasons.append(\n                    "Lớp hiện tại chưa phù hợp tiến trình liên năm "\n                    f"(nguồn năm trước: lớp {baseline_grade}; "\n                    f"điều tra hiện tại: lớp {current_grade})"\n                )\n\n        return reasons\n\n    # Cùng một năm học: giữ nguyên logic cũ, trường/lớp phải thống nhất.\n    if record.school_id is not None:\n        if int(record.school_id) != int(enrollment.school_id):\n            reasons.append(\n                "Trường điều tra khác trường trong dữ liệu học sinh"\n            )\n    else:\n        survey_school_name = _normalize_text(\n            record.school_name_reported\n        )\n        student_school_name = _normalize_text(\n            enrollment.school.name if enrollment.school else ""\n        )\n        if (\n            survey_school_name\n            and student_school_name\n            and survey_school_name != student_school_name\n        ):\n            reasons.append(\n                "Tên trường ghi trên phiếu khác dữ liệu học sinh"\n            )\n\n    if record.class_id is not None:\n        if int(record.class_id) != int(enrollment.class_id):\n            reasons.append(\n                "Lớp điều tra khác lớp trong dữ liệu học sinh"\n            )\n    else:\n        survey_class_name = _normalize_text(\n            record.class_name_reported\n        )\n        student_class_name = _normalize_text(\n            enrollment.classroom.name if enrollment.classroom else ""\n        )\n        if (\n            survey_class_name\n            and student_class_name\n            and survey_class_name != student_class_name\n        ):\n            reasons.append(\n                "Tên lớp ghi trên phiếu khác dữ liệu học sinh"\n            )\n\n    return reasons\n# === BAI31C2A_CROSS_YEAR_PROGRESSION_END ==='

OLD_CAN_WRITE = "    return is_admin_role(role_code) or role_code == TEACHER_ROLE_CODE"
NEW_CAN_WRITE = (
    "    return is_admin_role(role_code) or role_code in "
    "{SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}"
)

OLD_STUDENT_SCOPE = '    if role_code != TEACHER_ROLE_CODE:\n        return False\n    return db.scalar(\n        select(StudentEnrollment.id).where(\n            StudentEnrollment.student_id == student_id,\n            StudentEnrollment.school_year_id == baseline_year_id,\n            StudentEnrollment.school_id.in_(sorted(allowed_school_ids)),\n        )\n    ) is not None'
NEW_STUDENT_SCOPE = '    if role_code not in {SCHOOL_ROLE_CODE, TEACHER_ROLE_CODE}:\n        return False\n    return db.scalar(\n        select(StudentEnrollment.id).where(\n            StudentEnrollment.student_id == student_id,\n            StudentEnrollment.school_year_id == baseline_year_id,\n            StudentEnrollment.school_id.in_(sorted(allowed_school_ids)),\n        )\n    ) is not None'


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

        source_state = None
        try:
            source_state = con.execute(
                """
                SELECT
                    id,
                    target_school_year_id,
                    source_school_year_id,
                    commune_id,
                    status,
                    student_count,
                    enrollment_count,
                    class_count,
                    import_count
                FROM student_reconciliation_source_states
                WHERE target_school_year_id=2
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        except Exception:
            source_state = None
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )

    return integrity, len(fk), source_state


def replace_compare_school_class(text: str) -> str:
    pattern = re.compile(
        r"(?ms)^def _compare_school_class\(\n"
        r".*?"
        r"^def _compare_learning_status\("
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            "Không xác định duy nhất khối _compare_school_class "
            f"(tìm thấy {len(matches)})."
        )

    match = matches[0]
    replacement = (
        NEW_COMPARE_BLOCK
        + "\n\n\ndef _compare_learning_status("
    )
    return text[:match.start()] + replacement + text[match.end():]


def write_atomic(path: Path, content: str):
    tmp = path.with_name(path.name + ".bai31c2a.tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as out:
        log(out, "=" * 190)
        log(out, "BÀI 31C2A - HOÀN THIỆN ĐỐI CHIẾU HỌC SINH CẤP TRƯỜNG")
        log(out, "1) HỌC SINH CỦA TRƯỜNG ĐƯỢC TÌM TRONG DỮ LIỆU ĐIỀU TRA TOÀN XÃ")
        log(out, "2) LIÊN NĂM HIỂU LÊN LỚP / CHUYỂN CẤP, KHÔNG BÁO SAI TRƯỜNG MÁY MÓC")
        log(out, "3) MỞ QUYỀN XỬ LÝ CHO TÀI KHOẢN TRƯỜNG TRÊN MODULE ĐÃ CÓ")
        log(out, "KHÔNG TẠO ROUTE MỚI - KHÔNG GHI DATABASE KHI CÀI")
        log(out, "=" * 190)

        for path in (DB, MODULE):
            if not path.exists():
                raise RuntimeError(f"Không tìm thấy: {path}")

        db_sha_before = sha256_file(DB)
        module_sha_before = sha256_file(MODULE)
        integrity, fk_count, source_state = db_health()

        log(out, "DB_SHA_BEFORE =", db_sha_before)
        log(out, "MODULE_SHA_BEFORE =", module_sha_before)
        log(out, "INTEGRITY =", integrity)
        log(out, "FK_COUNT =", fk_count)
        log(out, "SOURCE_STATE =", source_state)

        if db_sha_before != EXPECTED_DB_SHA:
            raise RuntimeError(
                "DB không còn đúng nền 31C1B. Dừng an toàn."
            )
        if module_sha_before != EXPECTED_MODULE_SHA:
            raise RuntimeError(
                "student_survey_comparison.py không còn đúng nền 31C1B."
            )

        before = MODULE.read_text(encoding="utf-8-sig")

        required_tokens = [
            "SCHOOL_ROLE_CODE",
            "TEACHER_ROLE_CODE",
            "def _load_survey_rows(",
            "def _baseline_allowed_school_ids(",
            "def _load_scope_enrollments(",
            "def _build_comparison_rows(",
            "def _compare_school_class(",
            "def _compare_learning_status(",
            "def _can_write_resolution(",
            "def _can_manage_signoff(",
            'return is_admin_role(user.get("role_code"))',
            "StudentEnrollment.school_year_id == baseline_year_id",
            "StudentEnrollment.school_id.in_(sorted(allowed_school_ids))",
            "SO_DINH_DANH",
            "MA_HOC_SINH",
            "HO_TEN_NGAY_SINH_GIOI_TINH",
            "HO_TEN_NGAY_SINH",
        ]
        missing = [x for x in required_tokens if x not in before]
        if missing:
            raise RuntimeError(
                "Thiếu token nghiệp vụ nền: " + repr(missing)
            )

        if before.count(OLD_FORM_FILTER) != 1:
            raise RuntimeError(
                "Không xác định duy nhất dòng form_filters cần sửa."
            )
        if before.count(OLD_INDEX_BLOCK) != 1:
            raise RuntimeError(
                "Không xác định duy nhất block xây bảng đối chiếu."
            )
        if before.count(OLD_CAN_WRITE) != 1:
            raise RuntimeError(
                "Không xác định duy nhất quyền xử lý hiện tại."
            )
        if before.count(OLD_STUDENT_SCOPE) != 1:
            raise RuntimeError(
                "Không xác định duy nhất guard học sinh hiện tại."
            )

        after = before.replace(
            OLD_FORM_FILTER,
            NEW_FORM_FILTER,
            1,
        )
        after = after.replace(
            OLD_INDEX_BLOCK,
            NEW_INDEX_BLOCK,
            1,
        )
        after = replace_compare_school_class(after)
        after = after.replace(
            OLD_CAN_WRITE,
            NEW_CAN_WRITE,
            1,
        )
        after = after.replace(
            OLD_STUDENT_SCOPE,
            NEW_STUDENT_SCOPE,
            1,
        )

        ast.parse(after)

        markers = [
            "BAI31C2A_SCHOOL_FULL_COMMUNE_SURVEY_SCOPE_START",
            "BAI31C2A_SCHOOL_RELEVANT_SURVEY_ROWS_START",
            "BAI31C2A_SCHOOL_RELEVANCE_FILTER_START",
            "BAI31C2A_CROSS_YEAR_PROGRESSION_START",
        ]
        for marker in markers:
            if after.count(marker) != 1:
                raise RuntimeError(
                    f"Marker {marker} không đúng 1 lần."
                )

        protected_tokens = [
            "StudentEnrollment.school_year_id == baseline_year_id",
            "StudentEnrollment.school_id.in_(sorted(allowed_school_ids))",
            "_build_student_indexes(all_students.values())",
            "_find_candidates(person, indexes)",
            "SO_DINH_DANH",
            "MA_HOC_SINH",
            "HO_TEN_NGAY_SINH_GIOI_TINH",
            "HO_TEN_NGAY_SINH",
            'return is_admin_role(user.get("role_code"))',
        ]
        for token in protected_tokens:
            if token not in after:
                raise RuntimeError(
                    "Patch làm mất nghiệp vụ đã có: " + token
                )

        route_count_before = before.count("@router.")
        route_count_after = after.count("@router.")
        if route_count_after != route_count_before:
            raise RuntimeError(
                "Số route thay đổi ngoài phạm vi."
            )

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = BACKUPS / f"source_truoc_BAI31C2A_{stamp}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        backup_file = backup_dir / "student_survey_comparison.py"
        shutil.copy2(MODULE, backup_file)
        log(out, "SOURCE_BACKUP =", backup_dir)

        wrote = False
        try:
            write_atomic(MODULE, after)
            wrote = True

            py_compile.compile(str(MODULE), doraise=True)

            installed = MODULE.read_text(encoding="utf-8-sig")
            ast.parse(installed)

            for marker in markers:
                if installed.count(marker) != 1:
                    raise RuntimeError(
                        f"Hậu kiểm marker {marker} không đạt."
                    )

            if installed.count(NEW_CAN_WRITE) != 1:
                raise RuntimeError(
                    "Hậu kiểm quyền xử lý cấp trường không đạt."
                )

            if installed.count(NEW_STUDENT_SCOPE) != 1:
                raise RuntimeError(
                    "Hậu kiểm guard học sinh cấp trường không đạt."
                )

            if 'return is_admin_role(user.get("role_code"))' not in installed:
                raise RuntimeError(
                    "Quyền chốt kết quả bị thay đổi ngoài phạm vi."
                )

            integrity2, fk_count2, source_state2 = db_health()
            db_sha_after = sha256_file(DB)

            if db_sha_after != db_sha_before:
                raise RuntimeError(
                    "Database thay đổi trong lúc cài source."
                )
            if integrity2 != "ok" or fk_count2 != 0:
                raise RuntimeError(
                    "Database hậu kiểm không đạt."
                )

            log(out, "PY_COMPILE = PASS")
            log(out, "SCHOOL_SURVEY_SEARCH_SCOPE = FULL_COMMUNE_RELEVANT_ROWS_ONLY")
            log(out, "BASELINE_STUDENT_SCOPE = OWN_SCHOOL_PRESERVED")
            log(out, "CROSS_YEAR_SCHOOL_CHANGE = NOT_AUTO_ERROR")
            log(out, "GRADE_PROGRESSION = CHECK_WHEN_GRADE_CAN_BE_PARSED")
            log(out, "PRESCHOOL_AGE_CLASS = NOT_PARSED_AS_PRIMARY_GRADE")
            log(out, "SCHOOL_CAN_RESOLVE = YES")
            log(out, "TEACHER_EXISTING_PERMISSION = PRESERVED")
            log(out, "SIGNOFF_PERMISSION = UNCHANGED_ADMIN_ONLY")
            log(out, "MATCHING_LOGIC = PRESERVED")
            log(out, "SOURCE_STATE_AFTER =", source_state2)
            log(out, "DB_SHA_AFTER =", db_sha_after)
            log(out, "MODULE_SHA_AFTER =", sha256_file(MODULE))
            log(out, "DATABASE_WRITES_THIS_RUN = 0")
            log(out, "NEW_ROUTE_CREATED = NO")
            log(out, "BAI31C2A_SUCCESS = YES")
            log(out, "=" * 190)

        except Exception:
            if wrote:
                shutil.copy2(backup_file, MODULE)
            raise

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as out:
                log(out, "")
                log(out, "=" * 190)
                log(out, "BAI31C2A_SUCCESS = NO")
                log(out, "ERROR =", repr(exc))
                if DB.exists():
                    log(out, "DB_SHA_CURRENT =", sha256_file(DB))
                log(out, "DỪNG AN TOÀN.")
                log(out, "=" * 190)
        except Exception:
            print("ERROR =", repr(exc))
        raise
