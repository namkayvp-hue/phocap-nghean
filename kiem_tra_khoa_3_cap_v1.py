from __future__ import annotations

import hashlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


BATCH_TEST_ID = 114

REQUIRED_TABLES = {
    "survey_batches": {
        "id",
        "school_year_id",
        "commune_id",
        "status",
        "is_locked",
    },
    "survey_commune_execution_states": {
        "survey_batch_id",
        "is_commune_locked",
        "is_province_locked",
    },
    "survey_school_assignments": {
        "survey_batch_id",
        "school_id",
        "status",
        "is_locked",
    },
    "survey_execution_workflow_logs": {
        "survey_batch_id",
        "school_id",
        "action",
        "created_at",
    },
}

SOURCE_CHECKS = {
    "app/routers/survey_school_workflow.py": [
        '@router.post("/{batch_id}/phan-cong-truong/{school_id}/khoa")',
        '@router.post("/{batch_id}/phan-cong-truong/{school_id}/mo-khoa")',
        '@router.post("/{batch_id}/khoa-xa")',
        '@router.post("/{batch_id}/mo-khoa-xa")',
        '@router.post("/dieu-hanh-trien-khai/khoa-toan-tinh")',
        '@router.post("/dieu-hanh-trien-khai/mo-khoa-toan-tinh")',
        "CHOT_QUY_TAC_KHOA_TRUONG_100_PHAN_TRAM_V1",
    ],
    "app/access_control.py": [
        "def _kiem_tra_khoa_dot_dieu_tra(",
        "is_province_locked",
        "is_commune_locked",
        "survey_school_assignments",
        '"school_locked"',
    ],
    "app/main.py": [
        "survey_school_workflow_router",
    ],
    "app/survey_workflow_models.py": [
        "class SurveyCommuneExecutionState",
        "class SurveySchoolAssignment",
        "class SurveyExecutionWorkflowLog",
    ],
}


def find_project_root() -> Path:
    candidates = [
        Path.cwd(),
        Path(r"C:\PhoCap"),
        Path(__file__).resolve().parent,
    ]
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if str(candidate).lower() in seen:
            continue
        seen.add(str(candidate).lower())
        if (candidate / "app").is_dir() and (candidate / "app" / "main.py").is_file():
            return candidate
    raise SystemExit(
        "KHÔNG TÌM THẤY thư mục dự án. Hãy đặt file này trong C:\\PhoCap "
        "hoặc chạy PowerShell tại C:\\PhoCap."
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


class Reporter:
    def __init__(self):
        self.lines: list[str] = []

    def add(self, text: str = ""):
        self.lines.append(str(text))
        print(text)

    def section(self, title: str):
        self.add()
        self.add("=" * 110)
        self.add(title)
        self.add("=" * 110)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8-sig")


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def scalar(conn: sqlite3.Connection, sql: str, params=()):
    row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


def main() -> int:
    root = find_project_root()
    db_path = root / "data" / "phocap.db"
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    report_path = root / "exports" / f"bao_cao_kiem_tra_khoa_3_cap_v1_{stamp}.txt"

    r = Reporter()
    r.add("BỘ KIỂM TRA KHÓA 3 CẤP V1 - CHỈ ĐỌC, KHÔNG SỬA DỮ LIỆU")
    r.add(f"Thời gian: {now:%d/%m/%Y %H:%M:%S}")
    r.add(f"Dự án: {root}")
    r.add(f"Database: {db_path}")

    r.section("1. KIỂM TRA MÃ NGUỒN")
    source_ok = True
    for rel, markers in SOURCE_CHECKS.items():
        path = root / rel
        if not path.is_file():
            r.add(f"[THIẾU] {rel}")
            source_ok = False
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        r.add(f"[CÓ] {rel}")
        r.add(f"     SHA256: {sha256(path)}")
        for marker in markers:
            found = marker in text
            r.add(f"     {'ĐẠT' if found else 'THIẾU'}: {marker}")
            source_ok = source_ok and found

    if not db_path.is_file():
        r.section("2. KIỂM TRA DATABASE")
        r.add("[LỖI] Không tìm thấy C:\\PhoCap\\data\\phocap.db")
        r.save(report_path)
        r.add(f"\nĐã lưu báo cáo: {report_path}")
        return 2

    r.section("2. KIỂM TRA DATABASE")
    r.add(f"Dung lượng: {db_path.stat().st_size / (1024*1024):.2f} MB")

    db_ok = True
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")

        integrity = scalar(conn, "PRAGMA integrity_check")
        r.add(f"integrity_check: {integrity}")
        db_ok = db_ok and str(integrity).lower() == "ok"

        fk_rows = list(conn.execute("PRAGMA foreign_key_check"))
        r.add(f"foreign_key_check: {len(fk_rows)} lỗi")
        db_ok = db_ok and len(fk_rows) == 0

        for table, required_cols in REQUIRED_TABLES.items():
            if not table_exists(conn, table):
                r.add(f"[THIẾU BẢNG] {table}")
                db_ok = False
                continue
            cols = table_columns(conn, table)
            missing = sorted(required_cols - cols)
            r.add(
                f"[BẢNG] {table}: "
                + ("ĐẠT" if not missing else "THIẾU CỘT: " + ", ".join(missing))
            )
            db_ok = db_ok and not missing

        if table_exists(conn, "survey_batches"):
            r.add(f"Số đợt điều tra: {scalar(conn, 'SELECT COUNT(*) FROM survey_batches') or 0}")
        if table_exists(conn, "survey_commune_execution_states"):
            r.add(
                "Số trạng thái khóa xã/tỉnh: "
                f"{scalar(conn, 'SELECT COUNT(*) FROM survey_commune_execution_states') or 0}"
            )
        if table_exists(conn, "survey_school_assignments"):
            r.add(
                "Số nhiệm vụ trường: "
                f"{scalar(conn, 'SELECT COUNT(*) FROM survey_school_assignments') or 0}"
            )
        if table_exists(conn, "survey_execution_workflow_logs"):
            r.add(
                "Số dòng nhật ký quy trình: "
                f"{scalar(conn, 'SELECT COUNT(*) FROM survey_execution_workflow_logs') or 0}"
            )

        r.section(f"3. KIỂM TRA ĐỢT #{BATCH_TEST_ID}")
        batch = None
        if table_exists(conn, "survey_batches"):
            batch = conn.execute(
                """
                SELECT sb.id,
                       sb.code,
                       sb.status,
                       sb.is_locked,
                       sb.school_year_id,
                       sb.commune_id,
                       sy.name AS school_year_name,
                       c.name AS commune_name
                FROM survey_batches AS sb
                LEFT JOIN school_years AS sy ON sy.id = sb.school_year_id
                LEFT JOIN communes AS c ON c.id = sb.commune_id
                WHERE sb.id = ?
                """,
                (BATCH_TEST_ID,),
            ).fetchone()

        if batch is None:
            r.add(f"Không có đợt #{BATCH_TEST_ID} trong database hiện tại.")
        else:
            r.add(
                f"Đợt #{batch['id']} | mã={batch['code']} | "
                f"năm học={batch['school_year_name']} | xã={batch['commune_name']} | "
                f"status={batch['status']} | survey_batches.is_locked={batch['is_locked']}"
            )

            if table_exists(conn, "survey_commune_execution_states"):
                state = conn.execute(
                    """
                    SELECT is_commune_locked, is_province_locked,
                           commune_locked_at, province_locked_at
                    FROM survey_commune_execution_states
                    WHERE survey_batch_id = ?
                    """,
                    (BATCH_TEST_ID,),
                ).fetchone()
                if state:
                    r.add(
                        "Khóa phân tầng: "
                        f"xã={state['is_commune_locked']} | "
                        f"tỉnh={state['is_province_locked']} | "
                        f"commune_locked_at={state['commune_locked_at']} | "
                        f"province_locked_at={state['province_locked_at']}"
                    )
                else:
                    r.add("[CHƯA CÓ] survey_commune_execution_states cho đợt này.")

            if table_exists(conn, "survey_forms"):
                form_total = scalar(
                    conn,
                    "SELECT COUNT(*) FROM survey_forms WHERE survey_batch_id=?",
                    (BATCH_TEST_ID,),
                ) or 0
                completed_total = scalar(
                    conn,
                    """
                    SELECT COUNT(*) FROM survey_forms
                    WHERE survey_batch_id=? AND status='DA_HOAN_THANH'
                    """,
                    (BATCH_TEST_ID,),
                ) or 0
                r.add(
                    f"Phiếu toàn địa bàn: {completed_total}/{form_total} hoàn thành "
                    f"({(completed_total/form_total*100 if form_total else 0):.1f}%)"
                )

            if (
                table_exists(conn, "survey_school_assignments")
                and table_exists(conn, "schools")
            ):
                rows = conn.execute(
                    """
                    SELECT ssa.school_id,
                           s.name AS school_name,
                           ssa.status,
                           ssa.is_locked
                    FROM survey_school_assignments AS ssa
                    LEFT JOIN schools AS s ON s.id = ssa.school_id
                    WHERE ssa.survey_batch_id = ?
                    ORDER BY s.name, ssa.school_id
                    """,
                    (BATCH_TEST_ID,),
                ).fetchall()
                r.add(f"Trường có nhiệm vụ: {len(rows)}")
                for row in rows:
                    school_id = int(row["school_id"])
                    counts = {"form_total": 0, "completed_total": 0}
                    if (
                        table_exists(conn, "survey_forms")
                        and table_exists(conn, "survey_form_investigators")
                        and table_exists(conn, "users")
                    ):
                        cr = conn.execute(
                            """
                            SELECT
                                COUNT(DISTINCT sf.id) AS form_total,
                                COUNT(DISTINCT CASE
                                    WHEN sf.status='DA_HOAN_THANH' THEN sf.id
                                END) AS completed_total
                            FROM survey_forms AS sf
                            JOIN survey_form_investigators AS sfi
                                ON sfi.survey_form_id = sf.id
                            JOIN users AS u
                                ON u.id = sfi.user_id
                            WHERE sf.survey_batch_id = ?
                              AND u.school_id = ?
                              AND u.is_active = 1
                            """,
                            (BATCH_TEST_ID, school_id),
                        ).fetchone()
                        counts = dict(cr) if cr else counts
                    r.add(
                        f"  - {row['school_name'] or 'Trường #' + str(school_id)}: "
                        f"phiếu {counts.get('completed_total',0)}/{counts.get('form_total',0)} | "
                        f"status={row['status']} | is_locked={row['is_locked']}"
                    )

        r.section("4. KẾT LUẬN")
        if source_ok and db_ok:
            r.add("KẾT QUẢ: ĐẠT phần nền tảng kỹ thuật cho cơ chế khóa 3 cấp.")
            r.add(
                "Bước tiếp theo: kiểm tra điều kiện nghiệp vụ khóa trường -> khóa xã -> khóa Sở "
                "trên dữ liệu thực tế."
            )
        else:
            r.add("KẾT QUẢ: CHƯA ĐẠT. Xem các dòng [THIẾU]/[LỖI] phía trên.")

    finally:
        conn.close()

    r.save(report_path)
    print()
    print(f"ĐÃ LƯU BÁO CÁO: {report_path}")
    print("Hãy gửi file báo cáo .txt này cho ChatGPT.")
    return 0 if source_ok and db_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
