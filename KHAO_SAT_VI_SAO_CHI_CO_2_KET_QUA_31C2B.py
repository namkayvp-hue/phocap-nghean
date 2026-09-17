# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
DB = ROOT / "data" / "phocap.db"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "KHAO_SAT_VI_SAO_CHI_CO_2_KET_QUA_31C2B.txt"

TARGET_SCHOOL_NAME = "Trường Mầm non Nghi Diên"
TARGET_COMMUNE_ID = 114
BASELINE_YEAR_ID = 1
CURRENT_YEAR_ID = 2
TARGET_BATCH_ID = 114


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


def normalize_vi(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.casefold().strip()


def cols(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def table_names(con):
    return [
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 180)
        log(f, "BÀI 31C2B - KHẢO SÁT VÌ SAO TÀI KHOẢN TRƯỜNG MẦM NON NGHI DIÊN CHỈ THẤY 2 KẾT QUẢ ĐỐI CHIẾU")
        log(f, "CHỈ ĐỌC DATABASE - KHÔNG SỬA SOURCE - KHÔNG GHI DB")
        log(f, "=" * 180)

        if not DB.exists():
            raise RuntimeError(f"Không tìm thấy DB: {DB}")

        db_sha_before = sha256_file(DB)
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

            log(f, "DB_SHA_BEFORE =", db_sha_before)
            log(f, "INTEGRITY =", integrity)
            log(f, "FK_COUNT =", len(fk))

            if integrity != "ok" or fk:
                raise RuntimeError("DB health không đạt")

            # 1. Xác định đúng school_id của MN Nghi Diên.
            school_rows = []
            if "schools" in tables:
                s_cols = cols(con, "schools")
                wanted = [x for x in ("id", "name", "code", "commune_id", "is_active") if x in s_cols]
                all_rows = con.execute(
                    f'SELECT {", ".join(wanted)} FROM schools WHERE commune_id=? ORDER BY name',
                    (TARGET_COMMUNE_ID,),
                ).fetchall()
                target_norm = normalize_vi(TARGET_SCHOOL_NAME)
                for r in all_rows:
                    d = dict(r)
                    n = normalize_vi(str(d.get("name") or ""))
                    if "nghi dien" in n or target_norm in n:
                        school_rows.append(d)

            log(f, "")
            log(f, "I. CÁC TRƯỜNG NGHI DIÊN TRONG XÃ")
            log(f, json.dumps(school_rows, ensure_ascii=False, indent=2, default=str))

            target_school = None
            for row in school_rows:
                if normalize_vi(str(row.get("name") or "")) == normalize_vi(TARGET_SCHOOL_NAME):
                    target_school = row
                    break
            if target_school is None:
                raise RuntimeError("Không xác định được đúng Trường Mầm non Nghi Diên")

            school_id = int(target_school["id"])
            log(f, "TARGET_SCHOOL_ID =", school_id)

            # 2. Đếm enrollment đúng trường theo từng năm.
            log(f, "")
            log(f, "II. HỌC SINH / ENROLLMENT CỦA ĐÚNG TRƯỜNG")
            if "student_enrollments" in tables:
                for year_id, label in ((BASELINE_YEAR_ID, "2025-2026"), (CURRENT_YEAR_ID, "2026-2027")):
                    total = con.execute(
                        """
                        SELECT COUNT(*)
                        FROM student_enrollments
                        WHERE school_id=? AND school_year_id=?
                        """,
                        (school_id, year_id),
                    ).fetchone()[0]
                    current = con.execute(
                        """
                        SELECT COUNT(*)
                        FROM student_enrollments
                        WHERE school_id=? AND school_year_id=? AND COALESCE(is_current,1)=1
                        """,
                        (school_id, year_id),
                    ).fetchone()[0]
                    log(f, f"ENROLLMENT_{label}_TOTAL =", total)
                    log(f, f"ENROLLMENT_{label}_IS_CURRENT =", current)

                    sample = con.execute(
                        """
                        SELECT
                            e.id AS enrollment_id,
                            e.student_id,
                            e.class_id,
                            e.status,
                            e.is_current,
                            s.code AS student_code,
                            s.full_name,
                            s.personal_id,
                            c.name AS class_name
                        FROM student_enrollments e
                        JOIN students s ON s.id=e.student_id
                        LEFT JOIN classes c ON c.id=e.class_id
                        WHERE e.school_id=? AND e.school_year_id=?
                        ORDER BY s.full_name
                        LIMIT 20
                        """,
                        (school_id, year_id),
                    ).fetchall()
                    log(f, f"SAMPLE_{label} =", json.dumps(
                        [dict(r) for r in sample],
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ))

            # 3. Đếm enrollment baseline của tất cả trường trong xã để xem nguồn có thực sự nạp.
            log(f, "")
            log(f, "III. ENROLLMENT NGUỒN 2025-2026 THEO TRƯỜNG TRONG XÃ")
            if "student_enrollments" in tables and "schools" in tables:
                rows = con.execute(
                    """
                    SELECT sc.id AS school_id, sc.name,
                           COUNT(e.id) AS enrollment_count,
                           SUM(CASE WHEN COALESCE(e.is_current,1)=1 THEN 1 ELSE 0 END) AS current_count
                    FROM schools sc
                    LEFT JOIN student_enrollments e
                      ON e.school_id=sc.id AND e.school_year_id=?
                    WHERE sc.commune_id=?
                    GROUP BY sc.id, sc.name
                    HAVING COUNT(e.id) > 0
                    ORDER BY sc.name
                    """,
                    (BASELINE_YEAR_ID, TARGET_COMMUNE_ID),
                ).fetchall()
                log(f, json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2, default=str))

            # 4. Snapshot nguồn đã khóa.
            log(f, "")
            log(f, "IV. NGUỒN ĐỐI CHIẾU ĐÃ KHÓA")
            if "student_reconciliation_source_states" in tables:
                states = con.execute(
                    """
                    SELECT *
                    FROM student_reconciliation_source_states
                    WHERE target_school_year_id=? AND commune_id=?
                    ORDER BY id
                    """,
                    (CURRENT_YEAR_ID, TARGET_COMMUNE_ID),
                ).fetchall()
                log(f, json.dumps([dict(r) for r in states], ensure_ascii=False, indent=2, default=str))

            if "student_reconciliation_state_enrollments" in tables:
                sr_cols = cols(con, "student_reconciliation_state_enrollments")
                log(f, "STATE_ENROLLMENT_COLUMNS =", sr_cols)
                # In schema + counts theo school nếu có school_id.
                if "school_id" in sr_cols:
                    rows = con.execute(
                        """
                        SELECT school_id, COUNT(*) AS n
                        FROM student_reconciliation_state_enrollments
                        GROUP BY school_id
                        ORDER BY n DESC
                        """
                    ).fetchall()
                    log(f, "STATE_ENROLLMENT_COUNTS_BY_SCHOOL =", json.dumps(
                        [dict(r) for r in rows],
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ))

            # 5. Dữ liệu điều tra hiện tại trỏ đến đúng trường.
            log(f, "")
            log(f, "V. ĐỐI TƯỢNG ĐIỀU TRA 2026-2027 TRỎ ĐẾN TRƯỜNG MN NGHI DIÊN")
            if "survey_person_year_records" in tables:
                spr_cols = cols(con, "survey_person_year_records")
                wanted = [x for x in (
                    "id", "survey_person_id", "survey_form_id", "school_year_id",
                    "school_id", "class_id", "school_name_reported",
                    "class_name_reported", "learning_status"
                ) if x in spr_cols]
                rows = con.execute(
                    f"""
                    SELECT {", ".join("r."+x for x in wanted)},
                           p.full_name, p.date_of_birth, p.personal_id,
                           p.ministry_student_code
                    FROM survey_person_year_records r
                    JOIN survey_people p ON p.id=r.survey_person_id
                    WHERE r.school_year_id=? AND r.school_id=?
                    ORDER BY p.full_name
                    """,
                    (CURRENT_YEAR_ID, school_id),
                ).fetchall()
                log(f, "SURVEY_ROWS_FOR_TARGET_SCHOOL_COUNT =", len(rows))
                log(f, json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2, default=str))

            # 6. Kiểm tra hai đối tượng test theo SĐD nếu có.
            log(f, "")
            log(f, "VI. KIỂM TRA 2 ĐỐI TƯỢNG ĐANG HIỆN TRÊN MÀN HÌNH")
            if "survey_people" in tables:
                p_cols = cols(con, "survey_people")
                if "personal_id" in p_cols:
                    rows = con.execute(
                        """
                        SELECT id, code, full_name, date_of_birth, personal_id, ministry_student_code
                        FROM survey_people
                        WHERE personal_id IN ('DD-TEST-NL-010009', 'DD-TEST-NL-010002')
                        ORDER BY id
                        """
                    ).fetchall()
                    log(f, json.dumps([dict(r) for r in rows], ensure_ascii=False, indent=2, default=str))

                    if "students" in tables:
                        matches = con.execute(
                            """
                            SELECT id, code, full_name, date_of_birth, personal_id
                            FROM students
                            WHERE personal_id IN ('DD-TEST-NL-010009', 'DD-TEST-NL-010002')
                            ORDER BY id
                            """
                        ).fetchall()
                        log(f, "MATCHING_STUDENTS_BY_PERSONAL_ID =", json.dumps(
                            [dict(r) for r in matches],
                            ensure_ascii=False,
                            indent=2,
                            default=str,
                        ))

        finally:
            con.close()

        log(f, "")
        log(f, "=" * 180)
        log(f, "VII. KẾT LUẬN AN TOÀN")
        log(f, "=" * 180)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "SOURCE_WRITES_THIS_RUN = 0")
        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "AUDIT31C2B_SUCCESS = YES")
        log(f, "=" * 180)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 180)
                log(f, "AUDIT31C2B_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 180)
        except Exception:
            print("ERROR =", repr(exc))
        raise
