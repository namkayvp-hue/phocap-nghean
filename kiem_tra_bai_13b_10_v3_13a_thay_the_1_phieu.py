from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

DEFAULT_BATCH_ID = 3
DEFAULT_FORM_NUMBER = "CL-0003"
DEFAULT_SCHOOL_USERNAME = "truong_40413308"


def section(title: str) -> None:
    print()
    print("=" * 118)
    print(title)
    print("=" * 118)


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def table_columns(con: sqlite3.Connection, name: str) -> list[str]:
    return [
        row["name"]
        for row in con.execute(f'PRAGMA table_info("{name}")').fetchall()
    ]


def fetch_school(con: sqlite3.Connection, username: str):
    return con.execute(
        '''
        SELECT
            u.id AS user_id,
            u.username,
            u.full_name,
            u.school_id,
            s.name AS school_name
        FROM users u
        LEFT JOIN schools s ON s.id = u.school_id
        WHERE u.username = ?
        ''',
        (username,),
    ).fetchone()


def fetch_form(con: sqlite3.Connection, batch_id: int, form_number: str):
    cols = table_columns(con, "survey_forms")
    required = {"id", "survey_batch_id", "form_number", "household_id"}
    missing = required - set(cols)
    if missing:
        raise RuntimeError(
            "survey_forms thiếu cột bắt buộc: " + ", ".join(sorted(missing))
        )

    return con.execute(
        '''
        SELECT
            sf.id AS form_id,
            sf.form_number,
            sf.household_id
        FROM survey_forms sf
        WHERE sf.survey_batch_id = ?
          AND sf.form_number = ?
        ''',
        (batch_id, form_number),
    ).fetchone()


def fetch_household_summary(con: sqlite3.Connection, household_id: int | None) -> dict:
    if household_id is None or not table_exists(con, "households"):
        return {}

    cols = set(table_columns(con, "households"))
    candidates = {
        "household_code": ["code", "household_code", "ma_ho", "house_code"],
        "head_name": ["head_name", "householder_name", "chu_ho", "owner_name", "name"],
        "address": ["address", "dia_chi", "full_address"],
    }

    selected = {}
    for alias, names in candidates.items():
        for name in names:
            if name in cols:
                selected[alias] = name
                break

    if not selected:
        return {}

    select_parts = [f'"{col}" AS "{alias}"' for alias, col in selected.items()]
    sql = f'SELECT {", ".join(select_parts)} FROM households WHERE id = ?'
    row = con.execute(sql, (int(household_id),)).fetchone()
    return dict(row) if row else {}


def fetch_assignments(con: sqlite3.Connection, form_id: int):
    return con.execute(
        '''
        SELECT
            sfi.id AS investigator_id,
            sfi.order_number,
            sfi.is_primary,
            sfi.user_id,
            sfi.signed_at,
            sfi.notes,
            u.username,
            u.full_name,
            u.school_id,
            s.name AS school_name,
            r.code AS role_code,
            r.name AS role_name
        FROM survey_form_investigators sfi
        JOIN users u ON u.id = sfi.user_id
        LEFT JOIN schools s ON s.id = u.school_id
        LEFT JOIN roles r ON r.id = u.role_id
        WHERE sfi.survey_form_id = ?
        ORDER BY sfi.order_number, sfi.id
        ''',
        (form_id,),
    ).fetchall()


def fetch_logs(con: sqlite3.Connection, form_id: int):
    if not table_exists(con, "survey_assignment_logs"):
        return []

    cols = table_columns(con, "survey_assignment_logs")
    if "survey_form_id" not in cols:
        return []

    preferred = [
        "id",
        "survey_form_id",
        "action",
        "assignment_level",
        "actor_user_id",
        "target_user_id",
        "target_school_id",
        "notes",
        "created_at",
    ]
    select_cols = [c for c in preferred if c in cols]
    if not select_cols:
        return []

    sql = (
        "SELECT " + ", ".join(select_cols) +
        " FROM survey_assignment_logs WHERE survey_form_id = ? "
        "ORDER BY id DESC LIMIT 20"
    )
    return con.execute(sql, (form_id,)).fetchall()


def normalize_assignments(rows) -> list[dict]:
    return [
        {
            "investigator_id": row["investigator_id"],
            "order_number": row["order_number"],
            "is_primary": row["is_primary"],
            "user_id": row["user_id"],
            "username": row["username"],
            "full_name": row["full_name"],
            "school_id": row["school_id"],
            "school_name": row["school_name"],
            "role_code": row["role_code"],
        }
        for row in rows
    ]


def baseline_path(batch_id: int, form_number: str, school_id: int) -> Path:
    safe_form = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in form_number)
    return EXPORTS / f"v3_13_baseline_batch_{batch_id}_{safe_form}_school_{school_id}.json"


def print_assignments(rows) -> None:
    if not rows:
        print("(không có người điều tra)")
        return

    for row in rows:
        star = "★" if row["is_primary"] else " "
        print(
            f"{star} order={row['order_number']} | "
            f"{row['full_name']} | {row['username']} | "
            f"{row['role_code']} | school_id={row['school_id']} | "
            f"{row['school_name']}"
        )


def compare(baseline: list[dict], current: list[dict], own_school_id: int) -> None:
    section("6. SO SÁNH TRƯỚC / SAU")

    before_other = sorted(
        (x["school_id"], x["user_id"], x["username"])
        for x in baseline
        if x["school_id"] != own_school_id
    )
    after_other = sorted(
        (x["school_id"], x["user_id"], x["username"])
        for x in current
        if x["school_id"] != own_school_id
    )

    before_own = sorted(
        (x["user_id"], x["username"], x["full_name"])
        for x in baseline
        if x["school_id"] == own_school_id
    )
    after_own = sorted(
        (x["user_id"], x["username"], x["full_name"])
        for x in current
        if x["school_id"] == own_school_id
    )

    print("Hai trường còn lại giữ nguyên:", before_other == after_other)
    print("Nhân sự trường đang thao tác có thay đổi:", before_own != after_own)

    print("\nTrước - trường mình:")
    for x in before_own:
        print(" ", x)

    print("Sau - trường mình:")
    for x in after_own:
        print(" ", x)

    print("\nTrước - hai trường còn lại:")
    for x in before_other:
        print(" ", x)

    print("Sau - hai trường còn lại:")
    for x in after_other:
        print(" ", x)

    if before_other == after_other and before_own != after_own:
        print("\n=> ĐẠT: chỉ thay người thuộc chính trường đang thao tác.")
    elif before_other != after_other:
        print("\n=> KHÔNG ĐẠT: có thay đổi người của trường khác trong tổ.")
    else:
        print("\n=> CHƯA CÓ THAY ĐỔI ở nhân sự trường mình.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", type=int, default=DEFAULT_BATCH_ID)
    parser.add_argument("--form-number", default=DEFAULT_FORM_NUMBER)
    parser.add_argument("--school-username", default=DEFAULT_SCHOOL_USERNAME)
    parser.add_argument(
        "--reset-baseline",
        action="store_true",
        help="Xóa baseline cũ và ghi baseline mới.",
    )
    args = parser.parse_args()

    print("KIỂM TRA BÀI 13B-10 V3.13A - THAY THẾ/ĐIỀU CHỈNH 1 PHIẾU")
    print("CHỈ ĐỌC DATABASE; chỉ ghi file JSON baseline trong exports.")
    print("Không INSERT / UPDATE / DELETE dữ liệu nghiệp vụ.")
    print("V3.13A đã bỏ giả định households.household_code.")

    if not DB.exists():
        raise RuntimeError(f"Không tìm thấy database: {DB}")

    EXPORTS.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row

    try:
        school = fetch_school(con, args.school_username)
        if not school:
            raise RuntimeError(
                f"Không tìm thấy tài khoản trường: {args.school_username}"
            )

        form = fetch_form(con, args.batch_id, args.form_number)
        if not form:
            raise RuntimeError(
                f"Không tìm thấy phiếu {args.form_number} trong đợt #{args.batch_id}"
            )

        household = fetch_household_summary(con, form["household_id"])

        section("1. TRƯỜNG ĐANG KIỂM TRA")
        print(
            f"{school['school_name']} | username={school['username']} | "
            f"school_id={school['school_id']}"
        )

        section("2. PHIẾU ĐANG KIỂM TRA")
        print(
            f"form_id={form['form_id']} | form_number={form['form_number']} | "
            f"household_id={form['household_id']}"
        )
        if household:
            print("Thông tin hộ nhận diện được theo schema hiện tại:", household)

        rows = fetch_assignments(con, int(form["form_id"]))
        current = normalize_assignments(rows)

        section("3. PHÂN CÔNG HIỆN TẠI")
        print_assignments(rows)

        bp = baseline_path(
            args.batch_id,
            args.form_number,
            int(school["school_id"]),
        )

        if args.reset_baseline and bp.exists():
            bp.unlink()

        if not bp.exists():
            payload = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "batch_id": args.batch_id,
                "form_number": args.form_number,
                "form_id": form["form_id"],
                "household_id": form["household_id"],
                "school_username": args.school_username,
                "school_id": school["school_id"],
                "school_name": school["school_name"],
                "assignments": current,
            }
            bp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            section("4. ĐÃ GHI BASELINE")
            print(bp)
            print()
            print("Bây giờ trên giao diện:")
            print("  1) Mở phiếu này trong Giao phiếu cho giáo viên.")
            print("  2) Chọn 'Thay thế/điều chỉnh'.")
            print("  3) Chỉ thay giáo viên thuộc chính trường đang đăng nhập.")
            print("  4) Lưu/Giao phiếu.")
            print("  5) Chạy LẠI chính script này để so sánh.")
            return

        baseline_data = json.loads(bp.read_text(encoding="utf-8"))
        baseline = baseline_data["assignments"]

        section("4. BASELINE ĐÃ CÓ")
        print(
            f"Ghi lúc: {baseline_data.get('created_at')} | "
            f"File: {bp}"
        )

        section("5. NHẬT KÝ PHÂN CÔNG GẦN NHẤT")
        logs = fetch_logs(con, int(form["form_id"]))
        if not logs:
            print("(không đọc được nhật ký hoặc chưa có nhật ký)")
        else:
            for row in logs:
                print(dict(row))

        compare(
            baseline,
            current,
            int(school["school_id"]),
        )

        section("7. KẾT LUẬN")
        print("Nếu mục 6 báo ĐẠT, phần thay thế/điều chỉnh đã an toàn.")
        print(
            "Sau đó có thể xóa baseline bằng cách chạy lại với "
            "--reset-baseline để kiểm tra phiếu khác."
        )

    finally:
        con.close()


if __name__ == "__main__":
    main()
