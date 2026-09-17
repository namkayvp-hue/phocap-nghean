# -*- coding: utf-8 -*-
"""
DRY-RUN V2 - SAP NHAP TRUONG XA NGHI LOC THEO QD 3805/QD-UBND
==============================================================

CHI DOC DATABASE:
- SQLite mode=ro
- PRAGMA query_only=ON
- KHONG INSERT / UPDATE / DELETE / ALTER

MUC TIEU:
1) Phan loai cac bang KHONG co school_year_id theo dung dot 2026-2027.
2) Thong ke tai khoan theo vai tro de quyet dinh:
   - GIAO_VIEN: chuyen pham vi sang truong moi.
   - TRUONG: tai khoan truong cu se KHONG tu dong chuyen; de xuat khoa sau khi sap nhap.
3) Kiem tra bang to dieu tra / phan cong / nop danh sach theo survey_batch_id.
4) Kiem tra xung dot UNIQUE cua submission/assignment sau khi doi school_id.
5) Kiem tra school_name_reported trong survey_person_year_records 2026-2027.
6) KHONG thay doi phocap.db.

DAU RA:
C:\\PhoCap\\dry_run_sap_nhap_3805_Nghi_Loc_v2\\
C:\\PhoCap\\dry_run_sap_nhap_3805_Nghi_Loc_v2.zip
"""

from __future__ import annotations

import csv
import shutil
import sqlite3
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(r"C:\PhoCap")
DB_PATH = PROJECT_DIR / "data" / "phocap.db"
OUT_DIR = PROJECT_DIR / "dry_run_sap_nhap_3805_Nghi_Loc_v2"
OUT_ZIP = PROJECT_DIR / "dry_run_sap_nhap_3805_Nghi_Loc_v2.zip"
TARGET_YEAR_ID = 2

MAPPINGS = [
    (750, 748, "Mầm non Nghi Diên"),
    (751, 748, "Mầm non Nghi Diên"),
    (749, 747, "Mầm non TT Quán Hành"),
    (1181, 1178, "Tiểu học Nghi Diên"),
    (1180, 1179, "Tiểu học Nghi Trung"),
    (1608, 1605, "THCS Nghi Diên"),
    (1607, 1606, "THCS Nghi Trung"),
]

def q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'

def connect_ro() -> sqlite3.Connection:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn

def exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,)
    ).fetchone() is not None

def cols(conn: sqlite3.Connection, table: str) -> set[str]:
    if not exists(conn, table):
        return set()
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({q(table)})")}

def one(conn: sqlite3.Connection, sql: str, params=()):
    r = conn.execute(sql, params).fetchone()
    return None if r is None else r[0]

def school(conn: sqlite3.Connection, sid: int) -> dict[str, Any]:
    r = conn.execute(
        "SELECT id, code, name, commune_id, is_active FROM schools WHERE id=?",
        (sid,)
    ).fetchone()
    if not r:
        raise RuntimeError(f"Khong tim thay school_id={sid}")
    return dict(r)

def write_csv(path: Path, rows: list[dict[str, Any]], fields=None):
    if fields is None:
        fields = []
        seen = set()
        for r in rows:
            for k in r:
                if k not in seen:
                    seen.add(k); fields.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k:r.get(k,"") for k in fields})

def zip_dir(src: Path, dest: Path):
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(src))

def current_batches(conn: sqlite3.Connection) -> list[int]:
    if not exists(conn, "survey_batches"):
        return []
    return [
        int(r[0]) for r in conn.execute(
            "SELECT id FROM survey_batches WHERE school_year_id=? ORDER BY id",
            (TARGET_YEAR_ID,)
        )
    ]

def role_code_expr(conn: sqlite3.Connection) -> tuple[str, str]:
    # users.role_id -> roles.code theo cau truc hien tai.
    if exists(conn, "roles") and {"id","code"}.issubset(cols(conn,"roles")):
        return "LEFT JOIN roles r ON r.id=u.role_id", "COALESCE(r.code,'')"
    return "", "''"

def main() -> int:
    print("DRY-RUN V2 SAP NHAP TRUONG - XA NGHI LOC")
    print("- CHI DOC database; KHONG sua phocap.db.")
    print(f"- Database: {DB_PATH}")

    if not DB_PATH.exists():
        print("[LOI] Khong tim thay database.")
        return 2

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = connect_ro()
    try:
        batches = current_batches(conn)
        batch_set = set(batches)
        print(f"[NAM 2026-2027] survey_batch_id: {batches}")

        source_map = {s:(t,n) for s,t,n in MAPPINGS}
        schools = {sid:school(conn,sid) for pair in MAPPINGS for sid in pair[:2]}

        # -------------------------------------------------------
        # 1. TAI KHOAN
        # -------------------------------------------------------
        user_rows = []
        join_roles, role_expr = role_code_expr(conn)
        if exists(conn, "users"):
            ucols = cols(conn,"users")
            active_col = "u.is_active" if "is_active" in ucols else "1"
            for source_id, target_id, official_name in MAPPINGS:
                sql = f"""
                    SELECT
                        u.id, u.username,
                        COALESCE(u.full_name,'') AS full_name,
                        {role_expr} AS role_code,
                        {active_col} AS is_active
                    FROM users u
                    {join_roles}
                    WHERE u.school_id=?
                    ORDER BY role_code, u.id
                """
                for r in conn.execute(sql,(source_id,)):
                    role = str(r["role_code"] or "").upper()
                    if role == "GIAO_VIEN":
                        policy = "MOVE_TO_TARGET"
                    elif role in {"TRUONG","SCHOOL"}:
                        policy = "DISABLE_SOURCE_SCHOOL_ACCOUNT_REVIEW"
                    else:
                        policy = "REVIEW_ROLE"
                    user_rows.append({
                        "source_school_id":source_id,
                        "source_school_name":schools[source_id]["name"],
                        "target_school_id":target_id,
                        "target_school_name":schools[target_id]["name"],
                        "official_name_after_merger":official_name,
                        "user_id":r["id"],
                        "username":r["username"],
                        "full_name":r["full_name"],
                        "role_code":role,
                        "is_active":r["is_active"],
                        "proposed_policy":policy,
                    })
        write_csv(OUT_DIR/"01_TAI_KHOAN_THEO_VAI_TRO.csv", user_rows)

        # -------------------------------------------------------
        # 2. CAC BANG GAN TRUC TIEP survey_batch_id
        # -------------------------------------------------------
        direct_tables = [
            "survey_investigation_participants",
            "survey_participant_submissions",
            "survey_team_registration_logs",
            "survey_school_assignments",
            "survey_execution_workflow_logs",
        ]
        survey_rows = []
        conflict_rows = []

        for table in direct_tables:
            if not exists(conn,table):
                continue
            c = cols(conn,table)
            if not {"school_id","survey_batch_id"}.issubset(c):
                continue

            for source_id,target_id,official_name in MAPPINGS:
                sql = f"""
                    SELECT survey_batch_id, COUNT(*) AS n
                    FROM {q(table)}
                    WHERE school_id=?
                      AND survey_batch_id IN (
                          SELECT id FROM survey_batches WHERE school_year_id=?
                      )
                    GROUP BY survey_batch_id
                    ORDER BY survey_batch_id
                """
                for r in conn.execute(sql,(source_id,TARGET_YEAR_ID)):
                    policy = (
                        "KEEP_HISTORY"
                        if table in {"survey_team_registration_logs","survey_execution_workflow_logs"}
                        else "MOVE_CURRENT_BATCH"
                    )
                    survey_rows.append({
                        "table":table,
                        "source_school_id":source_id,
                        "source_school_name":schools[source_id]["name"],
                        "target_school_id":target_id,
                        "target_school_name":schools[target_id]["name"],
                        "official_name_after_merger":official_name,
                        "survey_batch_id":r["survey_batch_id"],
                        "rows":r["n"],
                        "proposed_policy":policy,
                    })

                    # Kiem tra UNIQUE(batch,school) cho submission/assignment.
                    if table in {"survey_participant_submissions","survey_school_assignments"}:
                        target_n = int(one(
                            conn,
                            f"SELECT COUNT(*) FROM {q(table)} WHERE school_id=? AND survey_batch_id=?",
                            (target_id,r["survey_batch_id"])
                        ) or 0)
                        if target_n:
                            conflict_rows.append({
                                "table":table,
                                "source_school_id":source_id,
                                "target_school_id":target_id,
                                "survey_batch_id":r["survey_batch_id"],
                                "source_rows":r["n"],
                                "target_rows":target_n,
                                "conflict":"YES",
                                "required_action":"MERGE_OR_SELECT_ONE_BEFORE_APPLY",
                            })

        write_csv(OUT_DIR/"02_DU_LIEU_DOT_2026_2027_KHONG_CO_NAM.csv", survey_rows)
        write_csv(
            OUT_DIR/"03_XUNG_DOT_PHAN_CONG_NOP_DANH_SACH.csv",
            conflict_rows,
            fields=[
                "table","source_school_id","target_school_id","survey_batch_id",
                "source_rows","target_rows","conflict","required_action"
            ]
        )

        # -------------------------------------------------------
        # 3. TEAM MEMBERS: team_id -> teams -> batch -> school_year
        # -------------------------------------------------------
        team_rows = []
        if exists(conn,"survey_investigation_team_members") and exists(conn,"survey_investigation_teams"):
            mc = cols(conn,"survey_investigation_team_members")
            tc = cols(conn,"survey_investigation_teams")
            if {"school_id","team_id"}.issubset(mc) and {"id","survey_batch_id"}.issubset(tc):
                for source_id,target_id,official_name in MAPPINGS:
                    rows = conn.execute("""
                        SELECT t.survey_batch_id, COUNT(*) AS n
                        FROM survey_investigation_team_members m
                        JOIN survey_investigation_teams t ON t.id=m.team_id
                        JOIN survey_batches b ON b.id=t.survey_batch_id
                        WHERE m.school_id=? AND b.school_year_id=?
                        GROUP BY t.survey_batch_id
                        ORDER BY t.survey_batch_id
                    """,(source_id,TARGET_YEAR_ID)).fetchall()
                    for r in rows:
                        team_rows.append({
                            "source_school_id":source_id,
                            "source_school_name":schools[source_id]["name"],
                            "target_school_id":target_id,
                            "target_school_name":schools[target_id]["name"],
                            "official_name_after_merger":official_name,
                            "survey_batch_id":r["survey_batch_id"],
                            "rows":r["n"],
                            "proposed_policy":"MOVE_CURRENT_BATCH",
                        })
        write_csv(OUT_DIR/"04_THANH_VIEN_TO_DIEU_TRA.csv",team_rows)

        # -------------------------------------------------------
        # 4. school_name_reported cua doi tuong nam 2026-2027
        # -------------------------------------------------------
        report_name_rows = []
        if exists(conn,"survey_person_year_records"):
            pc = cols(conn,"survey_person_year_records")
            if {"school_id","school_year_id"}.issubset(pc):
                has_name = "school_name_reported" in pc
                for source_id,target_id,official_name in MAPPINGS:
                    if has_name:
                        rows = conn.execute("""
                            SELECT COALESCE(school_name_reported,'') AS reported, COUNT(*) AS n
                            FROM survey_person_year_records
                            WHERE school_id=? AND school_year_id=?
                            GROUP BY COALESCE(school_name_reported,'')
                        """,(source_id,TARGET_YEAR_ID)).fetchall()
                        for r in rows:
                            report_name_rows.append({
                                "source_school_id":source_id,
                                "source_school_name":schools[source_id]["name"],
                                "target_school_id":target_id,
                                "official_name_after_merger":official_name,
                                "school_name_reported_current":r["reported"],
                                "rows":r["n"],
                                "proposed_policy":"UPDATE_TO_OFFICIAL_NAME_IF_RECORD_IS_2026_2027",
                            })
        write_csv(OUT_DIR/"05_TEN_TRUONG_TRONG_HO_SO_DOI_TUONG.csv",report_name_rows)

        # -------------------------------------------------------
        # 5. DOI NGU 2026-2027 theo nhom vi tri / trang thai
        # -------------------------------------------------------
        staff_rows = []
        if exists(conn,"staff_year_records"):
            sc = cols(conn,"staff_year_records")
            if {"school_id","school_year_id"}.issubset(sc):
                group_expr = "COALESCE(position_group,'')" if "position_group" in sc else "''"
                status_expr = "COALESCE(status_code,'')" if "status_code" in sc else "''"
                for source_id,target_id,official_name in MAPPINGS:
                    sql=f"""
                        SELECT {group_expr} AS position_group,
                               {status_expr} AS status_code,
                               COUNT(*) AS n
                        FROM staff_year_records
                        WHERE school_id=? AND school_year_id=?
                        GROUP BY {group_expr}, {status_expr}
                        ORDER BY 1,2
                    """
                    for r in conn.execute(sql,(source_id,TARGET_YEAR_ID)):
                        staff_rows.append({
                            "source_school_id":source_id,
                            "source_school_name":schools[source_id]["name"],
                            "target_school_id":target_id,
                            "official_name_after_merger":official_name,
                            "position_group":r["position_group"],
                            "status_code":r["status_code"],
                            "rows":r["n"],
                            "proposed_policy":"MOVE_2026_2027",
                        })
        write_csv(OUT_DIR/"06_DOI_NGU_2026_2027.csv",staff_rows)

        # -------------------------------------------------------
        # 6. FORM / LOP chi tiet
        # -------------------------------------------------------
        detail_rows=[]
        for table, extra_cols in [
            ("classes",["name"]),
            ("school_structured_report_inputs",["form_code"]),
            ("school_mn01_gv_inputs",[]),
            ("school_mn01_csvc_inputs",[]),
        ]:
            if not exists(conn,table):
                continue
            c=cols(conn,table)
            if not {"school_id","school_year_id"}.issubset(c):
                continue
            select_extra=[x for x in extra_cols if x in c]
            for source_id,target_id,official_name in MAPPINGS:
                sql="SELECT id"
                for x in select_extra:
                    sql+=f", {q(x)}"
                sql+=f" FROM {q(table)} WHERE school_id=? AND school_year_id=? ORDER BY id"
                for r in conn.execute(sql,(source_id,TARGET_YEAR_ID)):
                    item={
                        "table":table,
                        "source_school_id":source_id,
                        "source_school_name":schools[source_id]["name"],
                        "target_school_id":target_id,
                        "target_school_name":schools[target_id]["name"],
                        "official_name_after_merger":official_name,
                        "row_id":r["id"],
                    }
                    for x in select_extra:
                        item[x]=r[x]
                    detail_rows.append(item)
        write_csv(OUT_DIR/"07_CHI_TIET_LOP_VA_BIEU_2026_2027.csv",detail_rows)

        # -------------------------------------------------------
        # TONG QUAN
        # -------------------------------------------------------
        roles=defaultdict(int)
        for r in user_rows:
            roles[r["role_code"]]+=1

        total_current_survey=sum(int(r["rows"]) for r in survey_rows if r["proposed_policy"]=="MOVE_CURRENT_BATCH")
        total_logs=sum(int(r["rows"]) for r in survey_rows if r["proposed_policy"]=="KEEP_HISTORY")
        total_team=sum(int(r["rows"]) for r in team_rows)

        lines=[
            "DRY-RUN V2 SAP NHAP TRUONG QD 3805 - XA NGHI LOC",
            "="*78,
            "TRANG THAI: CHI DOC / KHONG SUA DATABASE",
            f"Nam hoc muc tieu: school_year_id={TARGET_YEAR_ID}",
            f"Survey batch 2026-2027: {batches}",
            "",
            "TAI KHOAN O CAC TRUONG NGUON",
        ]
        for role,n in sorted(roles.items()):
            lines.append(f"- {role or '(khong ro vai tro)'}: {n}")
        lines += [
            "",
            "DU LIEU KHONG CO school_year_id DA PHAN LOAI",
            f"- Dong thuoc dot 2026-2027 du kien chuyen: {total_current_survey}",
            f"- Dong log/nhat ky de nguyen: {total_logs}",
            f"- Thanh vien to dieu tra thuoc dot 2026-2027 du kien chuyen: {total_team}",
            f"- Xung dot submission/assignment: {len(conflict_rows)}",
            "",
            "NGUYEN TAC DE XUAT CHO BO CHUYEN THAT",
            "- GIAO_VIEN: doi school_id sang truong moi.",
            "- Tai khoan TRUONG cua truong nguon: khong gom vao tai khoan truong dich; de xuat khoa sau sap nhap.",
            "- survey_investigation_participants/team_members: chuyen neu thuoc batch 2026-2027.",
            "- survey_participant_submissions/school_assignments: chi chuyen neu khong trung (batch,target school).",
            "- workflow_logs/team_registration_logs: GIU NGUYEN de bao toan nhat ky lich su.",
            "- school_name_reported cua ban ghi 2026-2027: cap nhat ve ten truong moi khi ban ghi dang gan school_id nguon.",
            "- Du lieu truoc 2026-2027: KHONG thay doi.",
            "",
        ]
        if conflict_rows:
            lines.append("KET LUAN: CHUA DU DIEU KIEN APPLY - con xung dot can xu ly trong file 03.")
        else:
            lines.append("KET LUAN: Khong co xung dot submission/assignment truc tiep trong V2.")
        lines.append("Database phocap.db KHONG bi thay doi.")

        (OUT_DIR/"00_TONG_QUAN_V2.txt").write_text("\n".join(lines),encoding="utf-8")
        zip_dir(OUT_DIR,OUT_ZIP)

        print("")
        print("=== DRY-RUN V2 HOAN THANH ===")
        print(f"File gui lai ChatGPT: {OUT_ZIP}")
        print(f"Xung dot submission/assignment: {len(conflict_rows)}")
        print("Database phocap.db KHONG bi thay doi.")
        return 0
    except Exception as exc:
        print(f"[LOI] {type(exc).__name__}: {exc}")
        print("Database phocap.db KHONG bi thay doi.")
        return 1
    finally:
        conn.close()

if __name__=="__main__":
    raise SystemExit(main())
