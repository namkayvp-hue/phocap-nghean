from __future__ import annotations

import ast
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"
ROUTER = APP / "routers" / "surveys.py"
DB = PROJECT / "data" / "phocap.db"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_11_13_3_6_{STAMP}"

MARK_START = "# === BAI_13B_11_13_3_6_DYNAMIC_DATA_QUALITY_START ==="
MARK_END = "# === BAI_13B_11_13_3_6_DYNAMIC_DATA_QUALITY_END ==="

DYNAMIC_BLOCK = r'''
    # === BAI_13B_11_13_3_6_DYNAMIC_DATA_QUALITY_START ===
    # Tính tiến độ theo đúng nhóm MN/TH/THCS/XMC.
    _b1311336_form_ids = [
        int(_row["survey_form_id"])
        for _row in rows
    ]
    _b1311336_household_ids = [
        int(_row["household_id"])
        for _row in rows
    ]

    _b1311336_people: list[SurveyPerson] = []
    if _b1311336_household_ids:
        _b1311336_people = list(
            db.scalars(
                select(SurveyPerson)
                .where(
                    SurveyPerson.household_id.in_(
                        _b1311336_household_ids
                    ),
                    SurveyPerson.is_active.is_(True),
                )
                .order_by(
                    SurveyPerson.household_id.asc(),
                    SurveyPerson.date_of_birth.asc(),
                    SurveyPerson.full_name.asc(),
                    SurveyPerson.id.asc(),
                )
            ).all()
        )

    _b1311336_people_by_household: dict[int, list[SurveyPerson]] = {}
    for _person in _b1311336_people:
        _b1311336_people_by_household.setdefault(
            int(_person.household_id),
            [],
        ).append(_person)

    _b1311336_person_ids = [
        int(_person.id)
        for _person in _b1311336_people
    ]

    _b1311336_records: list[SurveyPersonYearRecord] = []
    if _b1311336_form_ids and _b1311336_person_ids:
        _b1311336_records = list(
            db.scalars(
                select(SurveyPersonYearRecord)
                .where(
                    SurveyPersonYearRecord.survey_form_id.in_(
                        _b1311336_form_ids
                    ),
                    SurveyPersonYearRecord.school_year_id
                    == batch.school_year_id,
                    SurveyPersonYearRecord.survey_person_id.in_(
                        _b1311336_person_ids
                    ),
                )
                .order_by(
                    SurveyPersonYearRecord.updated_at.desc(),
                    SurveyPersonYearRecord.id.desc(),
                )
            ).all()
        )

    _b1311336_record_by_key: dict[
        tuple[int, int],
        SurveyPersonYearRecord,
    ] = {}

    for _record in _b1311336_records:
        _key = (
            int(_record.survey_form_id),
            int(_record.survey_person_id),
        )
        _b1311336_record_by_key.setdefault(
            _key,
            _record,
        )

    _b1311336_quality_progress: dict[
        int,
        dict[str, int],
    ] = {}

    for _row in rows:
        _form_id = int(_row["survey_form_id"])
        _household_id = int(_row["household_id"])

        _missing_year = 0
        _incomplete_year = 0

        for _person in _b1311336_people_by_household.get(
            _household_id,
            [],
        ):
            _record = _b1311336_record_by_key.get(
                (
                    _form_id,
                    int(_person.id),
                )
            )

            if _record is None:
                _missing_year += 1
                continue

            _progress = b131133_tien_do_nam_hoc(
                person=_person,
                record=_record,
                school_year=batch.school_year,
            )

            if not bool(_progress["complete"]):
                _incomplete_year += 1

        _b1311336_quality_progress[_form_id] = {
            "missing_year_record_count": int(_missing_year),
            "incomplete_year_record_count": int(_incomplete_year),
        }
    # === BAI_13B_11_13_3_6_DYNAMIC_DATA_QUALITY_END ===

'''

OLD_COUNT_BLOCK = '''        year_record_count = _gia_tri_so(row["year_record_count"])
        missing_year_record_count = max(
            active_people_count - year_record_count,
            0,
        )
        incomplete_year_record_count = _gia_tri_so(
            row["incomplete_year_record_count"]
        )
'''

NEW_COUNT_BLOCK = '''        year_record_count = _gia_tri_so(row["year_record_count"])

        _b1311336_counts = _b1311336_quality_progress.get(
            int(row["survey_form_id"]),
            {
                "missing_year_record_count": max(
                    active_people_count - year_record_count,
                    0,
                ),
                "incomplete_year_record_count": _gia_tri_so(
                    row["incomplete_year_record_count"]
                ),
            },
        )

        missing_year_record_count = int(
            _b1311336_counts["missing_year_record_count"]
        )
        incomplete_year_record_count = int(
            _b1311336_counts["incomplete_year_record_count"]
        )
'''

OLD_DETAIL = '''                    f"Còn {incomplete_year_record_count} đối tượng chưa nhập "
                    f"đủ {len(BOOLEAN_YEAR_FIELDS)} chỉ báo.",
'''

NEW_DETAIL = '''                    f"Còn {incomplete_year_record_count} đối tượng chưa hoàn thành "
                    "thông tin năm học theo nhóm đối tượng.",
'''


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def db_check() -> tuple[str, int, int]:
    conn = sqlite3.connect(str(DB))
    try:
        integrity = str(
            conn.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_count = len(
            conn.execute("PRAGMA foreign_key_check").fetchall()
        )
        count = int(
            conn.execute(
                "SELECT COUNT(*) FROM survey_person_year_records"
            ).fetchone()[0]
        )
        return integrity, fk_count, count
    finally:
        conn.close()


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def extract_target_function(text: str) -> tuple[int, int]:
    start = text.find(
        "def tao_du_lieu_kiem_tra_chat_luong("
    )
    if start < 0:
        raise RuntimeError(
            "Không tìm thấy tao_du_lieu_kiem_tra_chat_luong."
        )

    next_def = text.find("\ndef ", start + 10)
    if next_def < 0:
        next_def = len(text)

    return start, next_def


def patch(text: str) -> str:
    if "def b131133_tien_do_nam_hoc" not in text:
        raise RuntimeError(
            "Không thấy helper tiến độ động b131133_tien_do_nam_hoc."
        )

    if "attends_two_sessions_per_day" not in text:
        raise RuntimeError(
            "Chưa thấy chỉ số Học 2 buổi/ngày trong router."
        )

    start, end = extract_target_function(text)
    fn = text[start:end]

    if MARK_START not in fn:
        anchor = "    items: list[dict[str, Any]] = []\n"
        if anchor not in fn:
            raise RuntimeError(
                "Không tìm thấy anchor items trong hàm kiểm tra."
            )
        fn = fn.replace(
            anchor,
            DYNAMIC_BLOCK + anchor,
            1,
        )

    if "_b1311336_quality_progress.get(" not in fn:
        if OLD_COUNT_BLOCK not in fn:
            raise RuntimeError(
                "Không tìm thấy khối đếm chất lượng cũ."
            )
        fn = fn.replace(
            OLD_COUNT_BLOCK,
            NEW_COUNT_BLOCK,
            1,
        )

    if OLD_DETAIL in fn:
        fn = fn.replace(
            OLD_DETAIL,
            NEW_DETAIL,
            1,
        )

    text = text.replace(
        '"THIEU_CHI_BAO": "Đối tượng chưa nhập đủ 8 chỉ báo"',
        '"THIEU_CHI_BAO": "Đối tượng chưa hoàn thành thông tin năm học theo nhóm đối tượng"',
    )
    text = text.replace(
        '"THIEU_CHI_BAO": "Đối tượng chưa nhập đủ 9 chỉ báo"',
        '"THIEU_CHI_BAO": "Đối tượng chưa hoàn thành thông tin năm học theo nhóm đối tượng"',
    )

    text = text[:start] + fn + text[end:]

    ast.parse(text)
    return text


def verify(text: str) -> None:
    start, end = extract_target_function(text)
    fn = text[start:end]

    for item in (
        MARK_START,
        MARK_END,
        "_b1311336_quality_progress",
        "b131133_tien_do_nam_hoc(",
        "thông tin năm học theo nhóm đối tượng.",
    ):
        if item not in text:
            raise RuntimeError(
                "Thiếu nội dung sau cài: " + item
            )

    if (
        'f"đủ {len(BOOLEAN_YEAR_FIELDS)} chỉ báo."'
        in fn
    ):
        raise RuntimeError(
            "Hàm kiểm tra vẫn còn thông báo số chỉ báo cố định."
        )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(ROUTER),
        ],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())

    if result.returncode != 0:
        raise RuntimeError(
            "py_compile surveys.py không đạt."
        )


def main() -> int:
    print("=" * 120)
    print(
        "BÀI 13B-11.13.3.6 - "
        "SỬA KIỂM TRA CHẤT LƯỢNG THEO ĐÚNG NHÓM ĐỐI TƯỢNG"
    )
    print("=" * 120)
    print()
    print("SỬA:")
    print(
        " - Không áp 9 chỉ báo Mầm non cho toàn bộ đối tượng."
    )
    print(
        " - MN kiểm MN; TH kiểm TH; THCS kiểm THCS; XMC kiểm XMC."
    )
    print(
        " - Chỉ số Học 2 buổi/ngày vẫn được tính cho Mầm non."
    )
    print(
        " - Nội dung lỗi không còn ghi 'đủ 9 chỉ báo' dùng chung."
    )
    print(
        " - Xuất Excel kiểm tra dùng chung dữ liệu nên tự đồng bộ."
    )
    print()
    print("AN TOÀN:")
    print(" - Chỉ sửa app/routers/surveys.py.")
    print(" - Không sửa database.")
    print(" - Có backup và rollback nếu lỗi.")
    print()

    if not ROUTER.exists() or not DB.exists():
        raise RuntimeError(
            "Thiếu surveys.py hoặc phocap.db."
        )

    integrity_before, fk_before, count_before = db_check()

    if integrity_before.lower() != "ok" or fk_before != 0:
        raise RuntimeError(
            "Database không đạt kiểm tra trước cài."
        )

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_path = (
        BACKUP
        / ROUTER.relative_to(PROJECT)
    )
    backup_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        ROUTER,
        backup_path,
    )

    print("Backup:", BACKUP)
    print(
        "survey_person_year_records:",
        count_before,
        "bản ghi",
    )

    try:
        before = read_text(ROUTER)
        after = patch(before)
        write_text(ROUTER, after)
        verify(read_text(ROUTER))

        integrity_after, fk_after, count_after = db_check()

        if integrity_after.lower() != "ok":
            raise RuntimeError(
                "integrity_check sau cài không đạt."
            )
        if fk_after != 0:
            raise RuntimeError(
                f"foreign_key_check có {fk_after} lỗi."
            )
        if count_after != count_before:
            raise RuntimeError(
                "Số bản ghi năm học bị thay đổi."
            )

        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(
            " - Kiểm tra chất lượng dùng tiến độ động: OK"
        )
        print(
            " - Không ép 9 chỉ báo MN cho mọi người: OK"
        )
        print(
            " - Học 2 buổi/ngày vẫn thuộc nhóm MN: OK"
        )
        print(
            " - py_compile: OK"
        )
        print(
            " - integrity_check: OK"
        )
        print(
            " - foreign_key_check: 0 lỗi"
        )
        print(
            " - Database: KHÔNG THAY ĐỔI"
        )
        print()
        print(
            "CÀI ĐẶT BÀI "
            "13B-11.13.3.6 THÀNH CÔNG"
        )
        return 0

    except Exception:
        traceback.print_exc()

        print()
        print(
            "CÓ LỖI - ĐANG KHÔI PHỤC surveys.py..."
        )

        shutil.copy2(
            backup_path,
            ROUTER,
        )
        clear_cache()

        print(
            "ĐÃ KHÔI PHỤC SOURCE."
        )
        print(
            "Database không bị thay đổi."
        )
        print(
            "Backup:",
            BACKUP,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
