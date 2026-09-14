from __future__ import annotations

import os
import re
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

DB = PROJECT / "data" / "phocap.db"
REPORT_ROUTER = (
    PROJECT
    / "app"
    / "routers"
    / "mn_official_reports.py"
)
SURVEY_ROUTER = (
    PROJECT
    / "app"
    / "routers"
    / "surveys.py"
)
MODEL = PROJECT / "app" / "survey_models.py"
YEAR_TEMPLATE = (
    PROJECT
    / "app"
    / "templates"
    / "surveys"
    / "year_records.html"
)

STAMP = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

OUT = (
    PROJECT
    / "exports"
    / f"khao_sat_bai_13b_11_13_4_0_mn01te_{STAMP}.txt"
)

FIELDS = (
    "disability_status",
    "disability_can_learn",
    "disability_access_education",
    "must_mobilize",
    "attends_two_sessions_per_day",
    "deceased_during_year",
    "completed_preschool_by_age",
    "completed_preschool_5",
)


def emit(lines: list[str], value: object = "") -> None:
    lines.append(str(value))


def section(lines: list[str], title: str) -> None:
    emit(lines)
    emit(lines, "=" * 118)
    emit(lines, title)
    emit(lines, "=" * 118)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(
        encoding="utf-8-sig",
        errors="replace",
    )


def table_exists(
    conn: sqlite3.Connection,
    name: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (name,),
    ).fetchone()

    return row is not None


def columns(
    conn: sqlite3.Connection,
    table: str,
) -> list[str]:
    if not table_exists(conn, table):
        return []

    return [
        str(row[1])
        for row in conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()
    ]


def scalar(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
) -> int:
    row = conn.execute(
        sql,
        params,
    ).fetchone()

    if row is None or row[0] is None:
        return 0

    return int(row[0])


def main() -> int:
    lines: list[str] = []

    emit(lines, "=" * 118)
    emit(
        lines,
        "BÀI 13B-11.13.4.0 - "
        "KHẢO SÁT NGUỒN DỮ LIỆU CHO BÁO CÁO MN-01-TE",
    )
    emit(lines, "=" * 118)
    emit(lines)
    emit(lines, "CHẾ ĐỘ: CHỈ ĐỌC")
    emit(lines, " - Không sửa source.")
    emit(lines, " - Không ALTER/INSERT/UPDATE/DELETE database.")
    emit(
        lines,
        " - Mục tiêu: chốt dữ liệu nào đã có, "
        "dữ liệu nào phải bổ sung và vì sao báo cáo đang 0.",
    )

    try:
        if not DB.exists():
            raise RuntimeError(
                f"Không tìm thấy DB: {DB}"
            )

        conn = sqlite3.connect(
            f"file:{DB.as_posix()}?mode=ro",
            uri=True,
        )

        try:
            section(
                lines,
                "1. KIỂM TRA DATABASE",
            )

            integrity = conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            fk_count = len(
                conn.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
            )

            emit(
                lines,
                f"integrity_check: {integrity}",
            )
            emit(
                lines,
                f"foreign_key_check: {fk_count} lỗi",
            )

            yr_cols = columns(
                conn,
                "survey_person_year_records",
            )

            emit(
                lines,
                "Các trường MN-01-TE cần kiểm tra:",
            )

            for field in FIELDS:
                emit(
                    lines,
                    f" - {field}: "
                    + (
                        "CÓ"
                        if field in yr_cols
                        else "CHƯA CÓ"
                    ),
                )

            section(
                lines,
                "2. NĂM HỌC 2026-2027",
            )

            years = []

            if table_exists(
                conn,
                "school_years",
            ):
                years = conn.execute(
                    """
                    SELECT id, code, name
                    FROM school_years
                    WHERE code='2026-2027'
                    ORDER BY id
                    """
                ).fetchall()

            emit(
                lines,
                f"school_years 2026-2027: {years}",
            )

            year_ids = [
                int(row[0])
                for row in years
            ]

            section(
                lines,
                "3. XÃ/PHƯỜNG NGHI LỘC",
            )

            commune_rows = []

            if table_exists(
                conn,
                "communes",
            ):
                commune_rows = conn.execute(
                    """
                    SELECT id, code, name
                    FROM communes
                    WHERE name LIKE '%Nghi Lộc%'
                       OR code LIKE '%NGHI%'
                    ORDER BY id
                    """
                ).fetchall()

            emit(
                lines,
                f"Communes khớp Nghi Lộc: {commune_rows}",
            )

            commune_ids = [
                int(row[0])
                for row in commune_rows
            ]

            section(
                lines,
                "4. ĐỢT ĐIỀU TRA / PHIẾU / ĐỐI TƯỢNG",
            )

            if (
                table_exists(
                    conn,
                    "survey_batches",
                )
                and year_ids
            ):
                placeholders = ",".join(
                    "?"
                    for _ in year_ids
                )

                batches = conn.execute(
                    f"""
                    SELECT
                        id,
                        code,
                        name,
                        school_year_id,
                        commune_id,
                        status
                    FROM survey_batches
                    WHERE school_year_id IN ({placeholders})
                    ORDER BY id
                    """,
                    tuple(year_ids),
                ).fetchall()

                emit(
                    lines,
                    f"Tổng batch năm 2026-2027: {len(batches)}",
                )

                target_batches = [
                    row
                    for row in batches
                    if (
                        int(row[4])
                        in commune_ids
                        if row[4] is not None
                        else False
                    )
                    or int(row[0]) == 114
                ]

                emit(
                    lines,
                    "Batch Nghi Lộc hoặc batch 114:",
                )

                for row in target_batches:
                    emit(
                        lines,
                        " - " + repr(row),
                    )

                    batch_id = int(
                        row[0]
                    )

                    forms = (
                        scalar(
                            conn,
                            """
                            SELECT COUNT(*)
                            FROM survey_forms
                            WHERE survey_batch_id=?
                            """,
                            (batch_id,),
                        )
                        if table_exists(
                            conn,
                            "survey_forms",
                        )
                        else 0
                    )

                    people = (
                        scalar(
                            conn,
                            """
                            SELECT COUNT(DISTINCT sp.id)
                            FROM survey_people sp
                            JOIN survey_forms sf
                              ON sf.household_id=sp.household_id
                            WHERE sf.survey_batch_id=?
                              AND COALESCE(sp.is_active,1)=1
                            """,
                            (batch_id,),
                        )
                        if (
                            table_exists(
                                conn,
                                "survey_people",
                            )
                            and table_exists(
                                conn,
                                "survey_forms",
                            )
                        )
                        else 0
                    )

                    records = (
                        scalar(
                            conn,
                            """
                            SELECT COUNT(*)
                            FROM survey_person_year_records spr
                            JOIN survey_forms sf
                              ON sf.id=spr.survey_form_id
                            WHERE sf.survey_batch_id=?
                            """,
                            (batch_id,),
                        )
                        if (
                            table_exists(
                                conn,
                                "survey_person_year_records",
                            )
                            and table_exists(
                                conn,
                                "survey_forms",
                            )
                        )
                        else 0
                    )

                    emit(
                        lines,
                        f"   forms={forms}, "
                        f"active_people={people}, "
                        f"year_records={records}",
                    )

            section(
                lines,
                "5. MÔ PHỎNG QUERY MN-01-TE",
            )

            if (
                year_ids
                and commune_ids
                and all(
                    table_exists(
                        conn,
                        name,
                    )
                    for name in (
                        "survey_people",
                        "survey_forms",
                        "survey_batches",
                        "survey_person_year_records",
                    )
                )
            ):
                for year_id in year_ids:
                    for commune_id in commune_ids:
                        count_current = scalar(
                            conn,
                            """
                            SELECT COUNT(DISTINCT sp.id)
                            FROM survey_people sp
                            JOIN survey_forms sf
                              ON sf.household_id=sp.household_id
                            JOIN survey_batches sb
                              ON sb.id=sf.survey_batch_id
                            LEFT JOIN survey_person_year_records spr
                              ON spr.survey_person_id=sp.id
                             AND spr.school_year_id=sb.school_year_id
                             AND spr.survey_form_id=sf.id
                            WHERE sb.school_year_id=?
                              AND COALESCE(sp.is_active,1)=1
                              AND sb.commune_id=?
                            """,
                            (
                                year_id,
                                commune_id,
                            ),
                        )

                        emit(
                            lines,
                            "Query hiện tại "
                            f"year_id={year_id}, "
                            f"commune_id={commune_id}: "
                            f"{count_current} đối tượng",
                        )

                        count_without_commune = scalar(
                            conn,
                            """
                            SELECT COUNT(DISTINCT sp.id)
                            FROM survey_people sp
                            JOIN survey_forms sf
                              ON sf.household_id=sp.household_id
                            JOIN survey_batches sb
                              ON sb.id=sf.survey_batch_id
                            WHERE sb.school_year_id=?
                              AND COALESCE(sp.is_active,1)=1
                            """,
                            (year_id,),
                        )

                        emit(
                            lines,
                            f"Không khóa commune: "
                            f"{count_without_commune} đối tượng",
                        )

            section(
                lines,
                "6. SOURCE BÁO CÁO MN-01-TE",
            )

            report_text = read_text(
                REPORT_ROUTER
            )

            emit(
                lines,
                f"mn_official_reports.py tồn tại: "
                f"{REPORT_ROUTER.exists()}",
            )

            checks = (
                "_query_te_people",
                "_te_metrics",
                "_fill_te_workbook",
                "attends_two_sessions_per_day",
                "completed_preschool_by_age",
                "disability_status",
                "disability_can_learn",
                "disability_access_education",
                "must_mobilize",
                "deceased_during_year",
            )

            for item in checks:
                emit(
                    lines,
                    f" - {item}: "
                    + (
                        "CÓ"
                        if item in report_text
                        else "CHƯA CÓ"
                    ),
                )

            old_warning = (
                "Hiện CSDL điều tra chưa có trường cấu trúc đủ chắc chắn"
            )

            emit(
                lines,
                " - Cảnh báo cũ còn tồn tại: "
                + (
                    "CÓ"
                    if old_warning
                    in report_text
                    else "KHÔNG"
                ),
            )

            section(
                lines,
                "7. SOURCE THÔNG TIN NĂM HỌC",
            )

            survey_text = read_text(
                SURVEY_ROUTER
            )
            model_text = read_text(
                MODEL
            )
            template_text = read_text(
                YEAR_TEMPLATE
            )

            for field in FIELDS:
                emit(
                    lines,
                    f"[{field}] "
                    f"model={'CÓ' if field in model_text else 'KHÔNG'} | "
                    f"router={'CÓ' if field in survey_text else 'KHÔNG'} | "
                    f"template={'CÓ' if field in template_text else 'KHÔNG'}",
                )

            section(
                lines,
                "8. KẾT LUẬN TỰ ĐỘNG",
            )

            existing = [
                field
                for field in FIELDS
                if field in yr_cols
            ]

            missing = [
                field
                for field in FIELDS
                if field not in yr_cols
            ]

            emit(
                lines,
                "Đã có trong DB: "
                + ", ".join(
                    existing
                ),
            )

            emit(
                lines,
                "Cần bổ sung vào DB: "
                + (
                    ", ".join(
                        missing
                    )
                    if missing
                    else "KHÔNG"
                ),
            )

            emit(lines)
            emit(
                lines,
                "Đề xuất Bài 13B-11.13.4.1:",
            )
            emit(
                lines,
                " - Tận dụng disability_status "
                "cho tổng trẻ khuyết tật.",
            )
            emit(
                lines,
                " - Tận dụng attends_two_sessions_per_day "
                "cho học 2 buổi/ngày.",
            )
            emit(
                lines,
                " - Tận dụng completed_preschool_by_age "
                "để tách hoàn thành CT GDMN tuổi 3, 4, 5.",
            )
            emit(
                lines,
                " - Chỉ tạo các trường thực sự còn thiếu.",
            )
            emit(
                lines,
                " - Sửa _query_te_people + _te_metrics "
                "+ _fill_te_workbook để tự điền đúng mẫu MN-01-TE.",
            )
            emit(
                lines,
                " - Đồng thời sửa nguyên nhân "
                "'Chưa tìm thấy dữ liệu điều tra' nếu query scope đang sai.",
            )

        finally:
            conn.close()

        OUT.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        OUT.write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

        print(
            "\n".join(
                lines[:90]
            )
        )

        if len(lines) > 90:
            print(
                "\n... báo cáo đầy đủ đã ghi ra file ..."
            )

        print()
        print("=" * 118)
        print(
            "KHẢO SÁT BÀI 13B-11.13.4.0 HOÀN THÀNH"
        )
        print("=" * 118)
        print(
            "Không có source/database nào bị thay đổi."
        )
        print("Báo cáo:")
        print(OUT)

        return 0

    except Exception:
        traceback.print_exc()

        try:
            OUT.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            lines.append("")
            lines.append(
                "KHẢO SÁT DỪNG DO LỖI."
            )
            lines.append(
                traceback.format_exc()
            )
            OUT.write_text(
                "\n".join(lines) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

        print(
            "Source/database không bị thay đổi."
        )
        print(
            "Báo cáo lỗi:",
            OUT,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
