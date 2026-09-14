from __future__ import annotations

import os
import sqlite3
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path


PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

REPORT = (
    EXPORTS
    / f"bao_cao_bai_13b_11_15_0_1_khao_sat_thcs_mo_rong_{STAMP}.txt"
)

YEAR_TABLE = "survey_person_year_records"
PEOPLE_TABLE = "survey_people"
EVENT_TABLE = "survey_person_events"

WANTED_FIELDS = {
    "Nơi học": (
        "thcs_study_location",
        "study_location_scope",
        "education_location_status",
    ),
    "Chương trình đang học": (
        "thcs_program_type",
        "education_program_type",
        "study_program_type",
        "current_program_type",
    ),
    "Bỏ học": (
        "is_dropout",
        "dropped_out",
        "dropout_status",
        "dropout_date",
    ),
    "Lưu ban": (
        "is_repeating_grade",
        "repeating_grade",
        "repeat_grade",
        "is_repeat_student",
    ),
    "Chưa đi học": (
        "never_attended_school",
        "not_yet_attended",
        "has_never_attended",
        "is_never_schooled",
    ),
}


def table_exists(
    conn: sqlite3.Connection,
    table: str,
) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table'
              AND name=?
            LIMIT 1
            """,
            (table,),
        ).fetchone()
        is not None
    )


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


def count(
    conn: sqlite3.Connection,
    table: str,
) -> int:
    return int(
        conn.execute(
            f'SELECT COUNT(*) FROM "{table}"'
        ).fetchone()[0]
    )


def add(
    out: list[str],
    text: str = "",
) -> None:
    out.append(text)


def distinct_values(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    limit: int = 50,
) -> list[tuple]:
    sql = (
        f'SELECT "{column}", COUNT(*) '
        f'FROM "{table}" '
        f'GROUP BY "{column}" '
        f'ORDER BY COUNT(*) DESC '
        f'LIMIT {int(limit)}'
    )

    return conn.execute(sql).fetchall()


def scan_source_terms() -> list[tuple[str, list[str]]]:
    terms = (
        "BO_HOC",
        "bỏ học",
        "LUU_BAN",
        "lưu ban",
        "CHUA_DI_HOC",
        "chưa đi học",
        "GDTX",
        "GDNN",
        "THPT",
        "post_lower_secondary_path",
        "learning_status",
    )

    results = []

    app = PROJECT / "app"

    for path in app.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in {
            ".py",
            ".html",
            ".htm",
        }:
            continue

        if any(
            part.lower() in {
                ".venv",
                "venv",
                "__pycache__",
                "backup",
                "backups",
            }
            for part in path.parts
        ):
            continue

        try:
            text = path.read_text(
                encoding="utf-8-sig",
                errors="ignore",
            )
        except Exception:
            continue

        found = [
            term
            for term in terms
            if term.lower() in text.lower()
        ]

        if found:
            results.append(
                (
                    str(
                        path.relative_to(PROJECT)
                    ),
                    found,
                )
            )

    return results


def main() -> int:
    print("=" * 132)
    print(
        "BÀI 13B-11.15.0.1 - "
        "KHẢO SÁT MỞ RỘNG NGUỒN THCS: "
        "BỎ HỌC / LƯU BAN / CHƯA ĐI HỌC / CHƯƠNG TRÌNH"
    )
    print("=" * 132)
    print()
    print("CẦN THU THẬP:")
    print(
        " - Tại chỗ / Đi học nơi khác / Nơi khác đến."
    )
    print(
        " - Bỏ học."
    )
    print(
        " - Lưu ban."
    )
    print(
        " - Chưa đi học."
    )
    print(
        " - Chương trình: THPT (phổ thông) / GDTX / GDNN / Khác."
    )
    print()
    print("MỤC TIÊU KHẢO SÁT:")
    print(
        " - Kiểm tra learning_status hiện có có thể tái sử dụng "
        "cho Bỏ học/Chưa đi học hay không."
    )
    print(
        " - Chỉ tạo field mới khi thực sự thiếu."
    )
    print(
        " - Bài này CHỈ ĐỌC, không sửa source/database."
    )
    print()

    if not DB.exists():
        raise RuntimeError(
            f"Không tìm thấy database: {DB}"
        )

    EXPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    out: list[str] = []

    add(out, "=" * 132)
    add(
        out,
        "BÁO CÁO BÀI 13B-11.15.0.1 - "
        "KHẢO SÁT MỞ RỘNG NGUỒN THCS",
    )
    add(out, "=" * 132)
    add(out, f"Project: {PROJECT}")
    add(out, f"Database: {DB}")
    add(
        out,
        f"Thời điểm: "
        f"{datetime.now():%d/%m/%Y %H:%M:%S}",
    )
    add(out)

    conn = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        integrity = str(
            conn.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk = conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        add(out, "I. KIỂM TRA DATABASE")
        add(out, "-" * 100)
        add(
            out,
            f"integrity_check: {integrity}",
        )
        add(
            out,
            f"foreign_key_check: {len(fk)} lỗi",
        )
        add(out)

        if not table_exists(
            conn,
            YEAR_TABLE,
        ):
            raise RuntimeError(
                f"Không tìm thấy bảng {YEAR_TABLE}."
            )

        year_cols = set(
            columns(
                conn,
                YEAR_TABLE,
            )
        )

        add(
            out,
            f"survey_person_year_records: "
            f"{count(conn, YEAR_TABLE)} bản ghi",
        )
        add(out)

        add(
            out,
            "II. CÁC TRƯỜNG NĂM HỌC HIỆN CÓ",
        )
        add(out, "-" * 100)

        for col in columns(
            conn,
            YEAR_TABLE,
        ):
            add(
                out,
                f" - {col}",
            )

        add(out)

        add(
            out,
            "III. KIỂM TRA learning_status",
        )
        add(out, "-" * 100)

        if "learning_status" in year_cols:
            values = distinct_values(
                conn,
                YEAR_TABLE,
                "learning_status",
            )

            add(
                out,
                "Các giá trị learning_status hiện có:",
            )

            for value, qty in values:
                add(
                    out,
                    f" - {value!r}: {qty}",
                )
        else:
            add(
                out,
                "Không có cột learning_status.",
            )

        add(out)

        add(
            out,
            "IV. KIỂM TRA post_lower_secondary_path",
        )
        add(out, "-" * 100)

        if (
            "post_lower_secondary_path"
            in year_cols
        ):
            values = distinct_values(
                conn,
                YEAR_TABLE,
                "post_lower_secondary_path",
            )

            for value, qty in values:
                add(
                    out,
                    f" - {value!r}: {qty}",
                )
        else:
            add(
                out,
                "Không có post_lower_secondary_path.",
            )

        add(out)

        add(
            out,
            "V. MA TRẬN FIELD CẦN CHO MẪU THCS",
        )
        add(out, "-" * 100)

        for label, candidates in WANTED_FIELDS.items():
            found = [
                col
                for col in candidates
                if col in year_cols
            ]

            if found:
                add(
                    out,
                    f"[CÓ] {label}: "
                    + ", ".join(found),
                )
            else:
                add(
                    out,
                    f"[CHƯA CÓ FIELD RIÊNG] {label}",
                )

        add(out)

        add(
            out,
            "VI. KIỂM TRA EVENT BIẾN ĐỘNG",
        )
        add(out, "-" * 100)

        if table_exists(
            conn,
            EVENT_TABLE,
        ):
            event_cols = columns(
                conn,
                EVENT_TABLE,
            )

            add(
                out,
                f"{EVENT_TABLE}: "
                f"{count(conn, EVENT_TABLE)} bản ghi",
            )

            for col in event_cols:
                add(
                    out,
                    f" - {col}",
                )

            for candidate in (
                "event_type",
                "event_code",
                "type_code",
            ):
                if candidate in event_cols:
                    add(out)
                    add(
                        out,
                        f"Giá trị {candidate}:",
                    )

                    for value, qty in distinct_values(
                        conn,
                        EVENT_TABLE,
                        candidate,
                    ):
                        add(
                            out,
                            f" - {value!r}: {qty}",
                        )
        else:
            add(
                out,
                "Không có survey_person_events.",
            )

    finally:
        conn.close()

    add(out)
    add(
        out,
        "VII. DẤU VẾT SOURCE LIÊN QUAN",
    )
    add(out, "-" * 100)

    for path, found in scan_source_terms():
        add(
            out,
            f" - {path}: "
            + ", ".join(found),
        )

    add(out)
    add(
        out,
        "VIII. PHƯƠNG ÁN DỮ LIỆU DỰ KIẾN SAU KHẢO SÁT",
    )
    add(out, "-" * 100)
    add(
        out,
        "1. thcs_study_location: "
        "CHUA_XAC_DINH / TAI_CHO / DI_HOC_NOI_KHAC / NOI_KHAC_DEN.",
    )
    add(
        out,
        "2. current_program_type hoặc thcs_program_type: "
        "CHUA_XAC_DINH / THPT / GDTX / GDNN / KHAC.",
    )
    add(
        out,
        "3. is_dropout: NULL / Có / Không "
        "CHỈ nếu learning_status chưa biểu diễn chắc chắn Bỏ học.",
    )
    add(
        out,
        "4. is_repeating_grade: NULL / Có / Không.",
    )
    add(
        out,
        "5. never_attended_school: NULL / Có / Không "
        "CHỈ nếu learning_status chưa biểu diễn chắc chắn Chưa đi học.",
    )
    add(
        out,
        "6. Không nhập tổng hợp theo tuổi/lớp bằng tay; báo cáo tự đếm.",
    )
    add(out)
    add(
        out,
        "CAM KẾT: KHẢO SÁT CHỈ ĐỌC, "
        "KHÔNG THAY ĐỔI SOURCE/DATABASE.",
    )

    REPORT.write_text(
        "\n".join(out),
        encoding="utf-8-sig",
    )

    print(
        "Khảo sát hoàn thành."
    )
    print(
        "Báo cáo:",
        REPORT,
    )
    print(
        "Database/source: KHÔNG THAY ĐỔI."
    )
    print(
        "integrity_check:",
        integrity,
    )
    print(
        "foreign_key_check:",
        len(fk),
        "lỗi",
    )
    print()
    print("=" * 132)
    print(
        "BÀI 13B-11.15.0.1 KHẢO SÁT THÀNH CÔNG"
    )
    print("=" * 132)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )
    except Exception:
        traceback.print_exc()
        print()
        print(
            "KHẢO SÁT GẶP LỖI. "
            "Bài này chỉ đọc nên source/database không bị thay đổi."
        )
        raise
