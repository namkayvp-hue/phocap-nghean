# -*- coding: utf-8 -*-
r"""
DRY-RUN V10.1 - KIỂM TRA DỮ LIỆU HIỂN THỊ TẠI TÀI KHOẢN NHÀ TRƯỜNG
SAU SÁP NHẬP QĐ 3805
====================================================================

MỤC TIÊU
--------
Sau khi V10 đã xác nhận sáp nhập database là đúng, V10.1 kiểm tra đúng lớp
"tài khoản Nhà trường nhìn thấy gì" tại 6 trường đích:

1. Tài khoản Trường đích có active hay không.
2. Đội ngũ 2026-2027:
   - tổng hồ sơ năm hiện hành;
   - hồ sơ ĐANG LÀM VIỆC + is_active=1;
   - Quản lý;
   - Giáo viên;
   - Nhân viên;
   - chưa phân loại;
   - trùng staff_member_id.
3. Với TH/THCS, mô phỏng đúng điều kiện lọc đang dùng ở
   /bieu-nhap/th-01-gv và /bieu-nhap/thcs-01-gv:
   - is_active=True
   - status_code=DANG_LAM_VIEC
   - lọc source_level / teaching_level theo cấp.
4. Lớp học năm hiện hành.
5. student_enrollments năm hiện hành.
6. survey_person_year_records.
7. CSVC, báo cáo và bảng nghiệp vụ theo năm.
8. Xuất bảng tổng hợp riêng từng trường để kiểm tra trên giao diện.

CHỈ ĐỌC:
- KHÔNG sửa database.
- KHÔNG sửa JSON.
- KHÔNG sửa mã nguồn.

CHẠY
----
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\kiem_tra_hien_thi_tai_khoan_nha_truong_sau_sap_nhap_QD3805_v10_1.py
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(r"C:\PhoCap")
DB_PATH = ROOT / "data" / "phocap.db"
PLAN_FILE = ROOT / "data" / "school_merger_approved_plans.json"


class AuditAbort(RuntimeError):
    pass


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def connect_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def all_tables(con: sqlite3.Connection) -> list[str]:
    return [
        str(r[0])
        for r in con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]


def colset(con: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(r[1])
        for r in con.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    }


def scalar(con: sqlite3.Connection, sql: str, params=()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def normalize(value) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        ch for ch in text
        if unicodedata.category(ch) != "Mn"
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def load_plans() -> list[dict]:
    if not PLAN_FILE.exists():
        raise AuditAbort(f"Không tìm thấy: {PLAN_FILE}")

    payload = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    plans = []

    for raw in payload.get("plans") or []:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "")
        doc = str(raw.get("document_code") or "")
        if not (pid.startswith("QD3805-") or "3805" in doc):
            continue

        item = dict(raw)
        item["school_year_id"] = int(item["school_year_id"])
        item["target_school_id"] = int(item["target_school_id"])
        item["source_school_ids"] = [
            int(x) for x in item.get("source_school_ids") or []
        ]
        item["level_code"] = str(item.get("level_code") or "").upper()
        plans.append(item)

    if len(plans) != 6:
        raise AuditAbort(f"QĐ 3805 phải có 6 nhóm, hiện có {len(plans)}.")

    return plans


def school_rows(con: sqlite3.Connection, ids: list[int]) -> dict[int, dict]:
    cs = colset(con, "schools")
    name_col = next(
        (c for c in ("name", "school_name", "ten_truong") if c in cs),
        None,
    )
    code_col = next(
        (c for c in ("code", "school_code", "ma_truong") if c in cs),
        None,
    )
    if not name_col:
        raise AuditAbort("Không xác định được tên trường.")

    select = [
        "id",
        f"{qident(name_col)} AS name",
        "is_active" if "is_active" in cs else "NULL AS is_active",
    ]
    select.append(
        f"{qident(code_col)} AS code" if code_col else "'' AS code"
    )

    marks = ",".join("?" for _ in ids)
    rows = con.execute(
        "SELECT " + ",".join(select)
        + f" FROM schools WHERE id IN ({marks})",
        ids,
    ).fetchall()

    return {
        int(r["id"]): {
            "id": int(r["id"]),
            "name": str(r["name"] or ""),
            "code": str(r["code"] or ""),
            "is_active": r["is_active"],
        }
        for r in rows
    }


def category_for_table(table: str) -> str:
    low = table.lower()

    if "staff" in low:
        return "DOI_NGU"
    if low == "classes" or low.startswith("class"):
        return "LOP_HOC"
    if "student" in low or "enrollment" in low:
        return "HOC_SINH"
    if low.startswith("survey_") or "investigation" in low:
        return "DIEU_TRA"
    if (
        "csvc" in low
        or "facility" in low
        or "infrastructure" in low
        or "equipment" in low
        or "sanitation" in low
        or "playground" in low
    ):
        return "CSVC"
    if "report" in low or "summary" in low:
        return "BAO_CAO"
    return "KHAC"


def staff_group(value) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"CBQL", "QUAN_LY", "MANAGEMENT"}:
        return "QUAN_LY"
    if raw in {"GIAO_VIEN", "GV", "TEACHER"}:
        return "GIAO_VIEN"
    if raw in {"NHAN_VIEN", "NV", "EMPLOYEE"}:
        return "NHAN_VIEN"

    norm = normalize(value)
    if any(x in norm for x in (
        "cbql", "quan ly", "hieu truong", "pho hieu truong"
    )):
        return "QUAN_LY"
    if "giao vien" in norm or "teacher" in norm:
        return "GIAO_VIEN"
    if "nhan vien" in norm or "employee" in norm:
        return "NHAN_VIEN"
    return "CHUA_XAC_DINH"


def ui_level_match(row: sqlite3.Row, level: str) -> bool:
    """
    Sao chép logic hiện tại của _structured_staff_row_matches_level()
    trong report_inputs.py cho TH/THCS.
    """
    level = str(level or "").upper()
    if level not in {"TH", "THCS"}:
        return True

    keys = set(row.keys())
    source_level = str(
        row["source_level"] if "source_level" in keys else ""
    ).strip().upper()
    teaching_level = str(
        row["teaching_level"] if "teaching_level" in keys else ""
    ).strip().upper()

    if level == "TH":
        if source_level == "TH":
            return True
        if teaching_level in {"TIEU_HOC", "LIEN_CAP_TH_THCS"}:
            return True
        return source_level not in {"THCS"}

    if level == "THCS":
        if source_level == "THCS":
            return True
        if teaching_level in {"THCS", "LIEN_CAP_TH_THCS"}:
            return True
        return source_level not in {"TH"}

    return True


def main() -> None:
    print("=" * 122)
    print("DRY-RUN V10.1 - KIỂM TRA HIỂN THỊ TẠI TÀI KHOẢN NHÀ TRƯỜNG")
    print("=" * 122)
    print("Chế độ: CHỈ ĐỌC")

    plans = load_plans()
    current_year_ids = {p["school_year_id"] for p in plans}
    if len(current_year_ids) != 1:
        raise AuditAbort("Không có một school_year_id duy nhất.")
    year_id = next(iter(current_year_ids))

    targets = sorted({p["target_school_id"] for p in plans})
    level_by_target = {
        p["target_school_id"]: p["level_code"]
        for p in plans
    }

    con = connect_ro(DB_PATH)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / f"dry_run_hien_thi_tai_khoan_truong_QD3805_v10_1_{ts}"
    out_dir.mkdir(parents=True, exist_ok=False)

    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()

        schools = school_rows(con, targets)
        tables = all_tables(con)

        staff_cols = colset(con, "staff_year_records") \
            if table_exists(con, "staff_year_records") else set()

        if "staff_year_records" not in tables:
            raise AuditAbort("Không có bảng staff_year_records.")

        school_summary = []
        staff_detail = []
        duplicate_detail = []
        ui_diff_rows = []
        problems = []

        for tid in targets:
            school = schools[tid]
            level = level_by_target.get(tid, "")

            # Tài khoản Trường active.
            active_school_login = 0
            if table_exists(con, "users"):
                active_school_login = scalar(
                    con,
                    "SELECT COUNT(*) FROM users "
                    "WHERE school_id=? AND username LIKE 'truong_%' "
                    "AND is_active=1",
                    (tid,),
                )

            # Đội ngũ năm hiện hành.
            staff_rows = con.execute(
                "SELECT * FROM staff_year_records "
                "WHERE school_id=? AND school_year_id=? "
                "ORDER BY id",
                (tid, year_id),
            ).fetchall()

            total_staff = len(staff_rows)

            active_working_rows = []
            ui_rows = []
            counts_all = Counter()
            counts_active = Counter()
            counts_ui = Counter()

            staff_member_ids = []

            for r in staff_rows:
                keys = set(r.keys())
                group = staff_group(
                    r["position_group"] if "position_group" in keys else ""
                )
                counts_all[group] += 1

                is_active = (
                    r["is_active"] in (1, True)
                    if "is_active" in keys
                    else True
                )
                status = str(
                    r["status_code"] if "status_code" in keys else ""
                ).strip().upper()

                active_working = is_active and (
                    not status or status == "DANG_LAM_VIEC"
                )

                if active_working:
                    active_working_rows.append(r)
                    counts_active[group] += 1

                    if ui_level_match(r, level):
                        ui_rows.append(r)
                        counts_ui[group] += 1

                smid = (
                    r["staff_member_id"]
                    if "staff_member_id" in keys else None
                )
                if smid is not None:
                    staff_member_ids.append(int(smid))

                staff_detail.append({
                    "target_school_id": tid,
                    "target_school_name": school["name"],
                    "level": level,
                    "record_id": r["id"] if "id" in keys else "",
                    "staff_member_id": smid if smid is not None else "",
                    "position_group": (
                        r["position_group"]
                        if "position_group" in keys else ""
                    ),
                    "classified_group": group,
                    "is_active": (
                        r["is_active"] if "is_active" in keys else ""
                    ),
                    "status_code": (
                        r["status_code"] if "status_code" in keys else ""
                    ),
                    "source_level": (
                        r["source_level"] if "source_level" in keys else ""
                    ),
                    "teaching_level": (
                        r["teaching_level"] if "teaching_level" in keys else ""
                    ),
                    "active_working": "YES" if active_working else "NO",
                    "matches_school_ui_level": (
                        "YES"
                        if active_working and ui_level_match(r, level)
                        else "NO"
                    ),
                })

            dup_ids = [
                sid for sid, n in Counter(staff_member_ids).items()
                if n > 1
            ]
            for sid in dup_ids:
                duplicate_detail.append({
                    "target_school_id": tid,
                    "target_school_name": school["name"],
                    "staff_member_id": sid,
                    "record_count": staff_member_ids.count(sid),
                })

            if dup_ids:
                problems.append(
                    f"{school['name']}: trùng {len(dup_ids)} staff_member_id."
                )

            # Các nhóm dữ liệu current-year theo từng school.
            current_by_category = defaultdict(int)
            current_by_table = {}

            for table in tables:
                cs = colset(con, table)
                if not {"school_id", "school_year_id"} <= cs:
                    continue

                n = scalar(
                    con,
                    f"SELECT COUNT(*) FROM {qident(table)} "
                    "WHERE school_id=? AND school_year_id=?",
                    (tid, year_id),
                )
                current_by_table[table] = n
                current_by_category[category_for_table(table)] += n

            classes = current_by_table.get("classes", 0)
            enrollments = current_by_table.get("student_enrollments", 0)
            survey_records = current_by_table.get(
                "survey_person_year_records", 0
            )

            # V10.1 không coi 0 lớp/HS là lỗi migration; chỉ đánh dấu GAP dữ liệu.
            data_gap_notes = []
            if classes == 0:
                data_gap_notes.append("CHƯA_CÓ_LỚP")
            if enrollments == 0:
                data_gap_notes.append("CHƯA_CÓ_ENROLLMENT")

            ui_diff = len(active_working_rows) - len(ui_rows)
            if ui_diff:
                ui_diff_rows.append({
                    "target_school_id": tid,
                    "target_school_name": school["name"],
                    "level": level,
                    "active_working_records": len(active_working_rows),
                    "ui_staff_records": len(ui_rows),
                    "difference": ui_diff,
                    "meaning": (
                        "Có hồ sơ active/working bị bộ lọc cấp học của "
                        "TH/THCS loại khỏi danh sách."
                    ),
                })

            school_summary.append({
                "target_school_id": tid,
                "target_school_name": school["name"],
                "level": level,
                "school_is_active": school["is_active"],
                "active_school_login": active_school_login,

                "staff_total_current": total_staff,
                "staff_active_working": len(active_working_rows),

                "quan_ly_all": counts_all["QUAN_LY"],
                "giao_vien_all": counts_all["GIAO_VIEN"],
                "nhan_vien_all": counts_all["NHAN_VIEN"],
                "chua_xac_dinh_all": counts_all["CHUA_XAC_DINH"],

                "quan_ly_active": counts_active["QUAN_LY"],
                "giao_vien_active": counts_active["GIAO_VIEN"],
                "nhan_vien_active": counts_active["NHAN_VIEN"],
                "chua_xac_dinh_active": counts_active["CHUA_XAC_DINH"],

                "ui_staff_count": len(ui_rows),
                "ui_quan_ly": counts_ui["QUAN_LY"],
                "ui_giao_vien": counts_ui["GIAO_VIEN"],
                "ui_nhan_vien": counts_ui["NHAN_VIEN"],
                "ui_chua_xac_dinh": counts_ui["CHUA_XAC_DINH"],

                "duplicate_staff_member_ids": len(dup_ids),

                "classes_current": classes,
                "student_enrollments_current": enrollments,
                "survey_person_year_records_current": survey_records,
                "csvc_current_rows": current_by_category["CSVC"],
                "report_current_rows": current_by_category["BAO_CAO"],
                "other_current_rows": current_by_category["KHAC"],

                "data_gap": " | ".join(data_gap_notes),
            })

            if active_school_login < 1:
                problems.append(
                    f"{school['name']}: không có tài khoản Trường active."
                )

            if counts_ui["CHUA_XAC_DINH"] > 0:
                problems.append(
                    f"{school['name']}: có {counts_ui['CHUA_XAC_DINH']} "
                    "hồ sơ đội ngũ đang hiển thị chưa phân loại."
                )

        # Gate.
        total_staff_current = sum(
            int(r["staff_total_current"]) for r in school_summary
        )
        total_staff_ui = sum(
            int(r["ui_staff_count"]) for r in school_summary
        )
        total_classes = sum(
            int(r["classes_current"]) for r in school_summary
        )
        total_enrollments = sum(
            int(r["student_enrollments_current"]) for r in school_summary
        )

        gate_rows = [
            {
                "check": "integrity_check",
                "result": "PASS" if integrity == "ok" else "FAIL",
                "detail": str(integrity),
            },
            {
                "check": "foreign_key_check",
                "result": "PASS" if not fk_errors else "FAIL",
                "detail": str(len(fk_errors)),
            },
            {
                "check": "target_school_count",
                "result": "PASS" if len(targets) == 6 else "FAIL",
                "detail": str(len(targets)),
            },
            {
                "check": "active_school_login_each_target",
                "result": (
                    "PASS"
                    if all(int(r["active_school_login"]) >= 1 for r in school_summary)
                    else "FAIL"
                ),
                "detail": "Mỗi trường đích phải có >=1 tài khoản Trường active.",
            },
            {
                "check": "duplicate_staff_member_id",
                "result": "PASS" if not duplicate_detail else "FAIL",
                "detail": str(len(duplicate_detail)),
            },
            {
                "check": "staff_unclassified_in_ui",
                "result": (
                    "PASS"
                    if all(int(r["ui_chua_xac_dinh"]) == 0 for r in school_summary)
                    else "FAIL"
                ),
                "detail": str(
                    sum(int(r["ui_chua_xac_dinh"]) for r in school_summary)
                ),
            },
            {
                "check": "staff_total_current",
                "result": "INFO",
                "detail": str(total_staff_current),
            },
            {
                "check": "staff_rows_expected_on_school_ui",
                "result": "INFO",
                "detail": str(total_staff_ui),
            },
            {
                "check": "classes_current",
                "result": "GAP" if total_classes == 0 else "INFO",
                "detail": str(total_classes),
            },
            {
                "check": "student_enrollments_current",
                "result": "GAP" if total_enrollments == 0 else "INFO",
                "detail": str(total_enrollments),
            },
        ]

        safe_staff_ui = (
            integrity == "ok"
            and not fk_errors
            and not duplicate_detail
            and all(
                int(r["active_school_login"]) >= 1
                and int(r["ui_chua_xac_dinh"]) == 0
                for r in school_summary
            )
        )

        write_csv(
            out_dir / "420_TONG_HOP_TAI_KHOAN_NHA_TRUONG.csv",
            list(school_summary[0].keys()),
            school_summary,
        )
        write_csv(
            out_dir / "421_CHI_TIET_STAFF_CURRENT.csv",
            [
                "target_school_id", "target_school_name", "level",
                "record_id", "staff_member_id",
                "position_group", "classified_group",
                "is_active", "status_code",
                "source_level", "teaching_level",
                "active_working", "matches_school_ui_level",
            ],
            staff_detail,
        )
        write_csv(
            out_dir / "422_TRUNG_STAFF_MEMBER_ID.csv",
            [
                "target_school_id", "target_school_name",
                "staff_member_id", "record_count",
            ],
            duplicate_detail,
        )
        write_csv(
            out_dir / "423_CHENH_LECH_BO_LOC_TH_THCS.csv",
            [
                "target_school_id", "target_school_name", "level",
                "active_working_records", "ui_staff_records",
                "difference", "meaning",
            ],
            ui_diff_rows,
        )
        write_csv(
            out_dir / "424_GATE_V10_1.csv",
            ["check", "result", "detail"],
            gate_rows,
        )

        summary = out_dir / "00_TONG_QUAN_V10_1.txt"
        with summary.open("w", encoding="utf-8") as f:
            f.write(
                "DRY-RUN V10.1 - DỮ LIỆU HIỂN THỊ TẠI TÀI KHOẢN NHÀ TRƯỜNG\n"
            )
            f.write("=" * 122 + "\n")
            f.write("CHỈ ĐỌC - KHÔNG SỬA DATABASE\n\n")

            f.write(f"Năm hiện hành: {year_id}\n")
            f.write(f"Số trường đích: {len(targets)}\n\n")

            f.write("ĐỘI NGŨ THEO TỪNG TRƯỜNG ĐÍCH\n")
            for r in school_summary:
                f.write(
                    f"- {r['target_school_id']} {r['target_school_name']}: "
                    f"DB={r['staff_total_current']}; "
                    f"đang làm việc={r['staff_active_working']}; "
                    f"UI={r['ui_staff_count']} "
                    f"(QL={r['ui_quan_ly']}, "
                    f"GV={r['ui_giao_vien']}, "
                    f"NV={r['ui_nhan_vien']}); "
                    f"Lớp={r['classes_current']}; "
                    f"Enrollment={r['student_enrollments_current']}\n"
                )

            f.write("\nTỔNG\n")
            f.write(f"- staff_year_records current: {total_staff_current}\n")
            f.write(f"- staff dự kiến hiển thị UI: {total_staff_ui}\n")
            f.write(f"- classes current: {total_classes}\n")
            f.write(f"- student_enrollments current: {total_enrollments}\n")
            f.write(f"- duplicate staff_member_id: {len(duplicate_detail)}\n")
            f.write(f"- chênh lệch do bộ lọc TH/THCS: {len(ui_diff_rows)} trường\n")

            f.write("\nCỔNG\n")
            for g in gate_rows:
                f.write(
                    f"- [{g['result']}] {g['check']}: {g['detail']}\n"
                )

            f.write("\nKẾT LUẬN\n")
            f.write(
                "SAFE_STAFF_DISPLAY_AT_SCHOOL_ACCOUNT = "
                + ("YES" if safe_staff_ui else "NO")
                + "\n"
            )
            if total_enrollments == 0:
                f.write(
                    "- GAP DỮ LIỆU: chưa có student_enrollments ở 6 trường đích; "
                    "đây là thiếu roster học sinh, không phải lỗi sáp nhập.\n"
                )
            if problems:
                f.write("\nVẤN ĐỀ CẦN KIỂM TRA\n")
                for p in problems:
                    f.write("- " + p + "\n")

        zip_path = ROOT / (
            f"dry_run_hien_thi_tai_khoan_truong_QD3805_v10_1_{ts}.zip"
        )
        with zipfile.ZipFile(
            zip_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            for p in sorted(out_dir.iterdir()):
                zf.write(p, arcname=p.name)

        print()
        print("=" * 122)
        print("HOÀN THÀNH DRY-RUN V10.1")
        print("=" * 122)
        print(f"Staff current DB: {total_staff_current}")
        print(f"Staff dự kiến hiển thị tại tài khoản Trường: {total_staff_ui}")
        print(f"Duplicate staff_member_id: {len(duplicate_detail)}")
        print(f"Trường có chênh do bộ lọc TH/THCS: {len(ui_diff_rows)}")
        print(f"Lớp hiện hành: {total_classes}")
        print(f"Student enrollments hiện hành: {total_enrollments}")
        print(
            "SAFE_STAFF_DISPLAY_AT_SCHOOL_ACCOUNT: "
            + ("YES" if safe_staff_ui else "NO")
        )
        print(f"ZIP: {zip_path}")
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")

    finally:
        con.close()


if __name__ == "__main__":
    try:
        main()
    except AuditAbort as exc:
        print()
        print("=" * 122)
        print("ĐÃ DỪNG DRY-RUN V10.1")
        print("=" * 122)
        print(str(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(2)
    except sqlite3.Error as exc:
        print()
        print("=" * 122)
        print("LỖI SQLITE TRONG V10.1")
        print("=" * 122)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(3)
    except Exception as exc:
        print()
        print("=" * 122)
        print("LỖI KHÔNG DỰ KIẾN TRONG V10.1")
        print("=" * 122)
        print(repr(exc))
        print("Database / JSON / mã nguồn: KHÔNG bị thay đổi.")
        sys.exit(4)
