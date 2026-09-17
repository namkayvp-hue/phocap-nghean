from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
DB = PROJECT / "data" / "phocap.db"
OUT = PROJECT / "chan_doan_TH02_Nghi_Loc.txt"

TARGET_COMMUNE_ID = 17827
TARGET_COMMUNE_TEXT = "Nghi Lộc"
TARGET_YEAR_CODE = "2026-2027"


def norm(s):
    return " ".join(str(s or "").strip().split())


def table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def columns(conn, table):
    if not table_exists(conn, table):
        return []
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def jdumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def parse_json(raw):
    try:
        obj = json.loads(raw or "{}")
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def year_start(code):
    m = re.search(r"(20\d{2})", str(code or ""))
    return int(m.group(1)) if m else 0


def class_grade(name):
    text = norm(name).upper()
    m = re.search(r"(?<!\d)(1[0-2]|[1-9])(?=[A-Z]|\b|\s|/|-|$)", text)
    return int(m.group(1)) if m else None


def safe_query(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except Exception as exc:
        return [("<LOI>", str(exc))]


def main():
    lines = []
    p = lines.append
    p("CHAN DOAN TH-02 CAP XA - CHI DOC DATABASE")
    p("=" * 78)
    p(f"Database: {DB}")
    if not DB.exists():
        p("[LOI] Khong tim thay database.")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 2

    uri = DB.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")

    # Commune
    commune = None
    if table_exists(conn, "communes"):
        commune = conn.execute(
            "SELECT id, code, name FROM communes WHERE id=?", (TARGET_COMMUNE_ID,)
        ).fetchone()
        if commune is None:
            commune = conn.execute(
                "SELECT id, code, name FROM communes WHERE name LIKE ? ORDER BY id LIMIT 1",
                (f"%{TARGET_COMMUNE_TEXT}%",),
            ).fetchone()
    if commune is None:
        p("[LOI] Khong tim thay xa Nghi Loc trong bang communes.")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 3

    commune_id = int(commune["id"])
    p(f"Xa: id={commune_id}, code={commune['code']}, name={commune['name']}")

    # Years
    years = []
    if table_exists(conn, "school_years"):
        years = conn.execute(
            "SELECT id, code, name FROM school_years ORDER BY id"
        ).fetchall()
    target_year = next((r for r in years if norm(r["code"]) == TARGET_YEAR_CODE), None)
    if target_year is None:
        target_year = max(years, key=lambda r: year_start(r["code"])) if years else None
    if target_year is None:
        p("[LOI] Khong tim thay nam hoc.")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("\n".join(lines))
        return 4

    target_year_id = int(target_year["id"])
    target_start = year_start(target_year["code"])
    p(f"Nam hoc dich: id={target_year_id}, code={target_year['code']}")
    prior_years = sorted(
        [r for r in years if year_start(r["code"]) <= target_start],
        key=lambda r: year_start(r["code"]),
        reverse=True,
    )[:4]
    p("Nam duoc doi chieu: " + ", ".join(f"{r['code']}(id={r['id']})" for r in prior_years))

    # Schools in commune
    schools = conn.execute(
        "SELECT id, code, name FROM schools WHERE commune_id=? AND COALESCE(is_active,1)=1 ORDER BY name",
        (commune_id,),
    ).fetchall()

    network_th_ids = set()
    if table_exists(conn, "school_network_year_data"):
        for r in conn.execute(
            "SELECT DISTINCT school_id FROM school_network_year_data WHERE level_code='TH'"
        ).fetchall():
            network_th_ids.add(int(r[0]))

    class_th_ids = set()
    if table_exists(conn, "classes"):
        rows = conn.execute(
            "SELECT school_id, name FROM classes WHERE school_year_id=? AND COALESCE(is_active,1)=1",
            (target_year_id,),
        ).fetchall()
        for r in rows:
            g = class_grade(r["name"])
            if g is not None and 1 <= g <= 5:
                class_th_ids.add(int(r["school_id"]))

    th_schools = []
    for s in schools:
        name_u = norm(s["name"]).upper()
        sid = int(s["id"])
        if sid in network_th_ids or sid in class_th_ids or "TIỂU HỌC" in name_u or "TIEU HOC" in name_u:
            th_schools.append(s)

    p("")
    p(f"So truong dang hoat dong trong xa: {len(schools)}")
    p(f"So truong duoc nhan dien cap TH: {len(th_schools)}")
    if not th_schools:
        p("[CANH BAO] Khong nhan dien duoc truong TH.")

    # Tables/columns summary
    p("")
    p("CAC BANG NGUON:")
    for t in [
        "school_structured_report_inputs",
        "staff_year_records",
        "staff_members",
        "school_network_year_data",
        "classes",
    ]:
        p(f"- {t}: {'CO' if table_exists(conn, t) else 'KHONG'}; cot={columns(conn,t)}")

    for s in th_schools:
        sid = int(s["id"])
        p("")
        p("#" * 78)
        p(f"TRUONG: id={sid}, code={s['code']}, name={s['name']}")

        # Class counts current
        if table_exists(conn, "classes"):
            crows = conn.execute(
                "SELECT name FROM classes WHERE school_id=? AND school_year_id=? AND COALESCE(is_active,1)=1 ORDER BY name",
                (sid, target_year_id),
            ).fetchall()
            grades = [g for g in (class_grade(r["name"]) for r in crows) if g is not None]
            p(f"Lop nam hien tai: tong={len(crows)}, lop 1-5={sum(1 for g in grades if 1<=g<=5)}, ten={[r['name'] for r in crows]}")

        # Structured forms current and prior
        if table_exists(conn, "school_structured_report_inputs"):
            p("TH-01-GV / TH-01-CSVC da luu:")
            rows = conn.execute(
                """
                SELECT sri.school_year_id, sy.code AS year_code, sri.form_code, sri.data_json, sri.updated_at
                FROM school_structured_report_inputs sri
                LEFT JOIN school_years sy ON sy.id=sri.school_year_id
                WHERE sri.school_id=? AND sri.form_code IN ('TH_01_GV','TH_01_CSVC')
                ORDER BY sy.id DESC, sri.form_code
                """,
                (sid,),
            ).fetchall()
            if not rows:
                p("  - KHONG CO BAN GHI structured cho TH_01_GV/TH_01_CSVC")
            for r in rows:
                data = parse_json(r["data_json"])
                p(f"  - {r['form_code']} | {r['year_code']} (year_id={r['school_year_id']}) | updated={r['updated_at']}")
                p(f"    keys={sorted(data.keys())}")
                # Print the fields relevant to condition assessment, plus all if small.
                interesting = {}
                relevant_prefixes = (
                    "pcgd_", "teacher_", "qual_", "prof_", "class_", "room_",
                    "principal_", "vice_", "office_", "health_", "team_", "meeting_",
                    "library_", "equipment_", "playground_", "sports_", "student_toilet_", "teacher_toilet_",
                )
                for k, v in data.items():
                    if k.startswith(relevant_prefixes):
                        interesting[k] = v
                p(f"    gia_tri_lien_quan={jdumps(interesting)}")

        # Staff current and prior distributions
        if table_exists(conn, "staff_year_records"):
            p("DOI NGU:")
            for yr in prior_years:
                yid = int(yr["id"])
                rows = conn.execute(
                    """
                    SELECT syr.position_group, syr.teaching_level, syr.source_level,
                           syr.qualification_level, syr.qualification_standard,
                           syr.professional_standard, syr.status_code, syr.is_active
                    FROM staff_year_records syr
                    WHERE syr.school_id=? AND syr.school_year_id=? AND COALESCE(syr.is_active,1)=1
                    """,
                    (sid, yid),
                ).fetchall()
                if not rows:
                    continue
                teachers = [r for r in rows if norm(r["position_group"]).upper().replace("_", " ") == "GIAO VIEN"]
                p(f"  - {yr['code']}: tong={len(rows)}, GV={len(teachers)}")
                p(f"    qualification_level={dict(Counter(norm(r['qualification_level']) for r in teachers))}")
                p(f"    qualification_standard={dict(Counter(norm(r['qualification_standard']) for r in teachers))}")
                p(f"    professional_standard={dict(Counter(norm(r['professional_standard']) for r in teachers))}")
                p(f"    teaching_level={dict(Counter(norm(r['teaching_level']) for r in teachers))}")
                p(f"    source_level={dict(Counter(norm(r['source_level']) for r in teachers))}")

        # Network data current/prior
        if table_exists(conn, "school_network_year_data"):
            p("DU LIEU MANG LUOI TH:")
            rows = conn.execute(
                """
                SELECT snyd.school_year_id, sy.code AS year_code, snyd.data_json, snyd.source_name
                FROM school_network_year_data snyd
                LEFT JOIN school_years sy ON sy.id=snyd.school_year_id
                WHERE snyd.school_id=? AND snyd.level_code='TH'
                ORDER BY sy.id DESC
                """,
                (sid,),
            ).fetchall()
            if not rows:
                p("  - KHONG CO")
            for r in rows[:5]:
                data = parse_json(r["data_json"])
                p(f"  - {r['year_code']} (year_id={r['school_year_id']}) source={r['source_name']}")
                p(f"    keys={sorted(data.keys())}")
                p(f"    data={jdumps(data)}")

    # Global quick diagnosis
    p("")
    p("=" * 78)
    p("TOM TAT NHANH")
    missing_gv_forms = 0
    missing_csvc_forms = 0
    for s in th_schools:
        sid = int(s["id"])
        if table_exists(conn, "school_structured_report_inputs"):
            gv = conn.execute(
                "SELECT COUNT(*) FROM school_structured_report_inputs WHERE school_id=? AND form_code='TH_01_GV'",
                (sid,),
            ).fetchone()[0]
            cs = conn.execute(
                "SELECT COUNT(*) FROM school_structured_report_inputs WHERE school_id=? AND form_code='TH_01_CSVC'",
                (sid,),
            ).fetchone()[0]
            missing_gv_forms += 0 if gv else 1
            missing_csvc_forms += 0 if cs else 1
    p(f"Truong TH khong co bat ky TH_01_GV structured: {missing_gv_forms}/{len(th_schools)}")
    p(f"Truong TH khong co bat ky TH_01_CSVC structured: {missing_csvc_forms}/{len(th_schools)}")
    p("Ket qua nay CHI DOC, khong INSERT/UPDATE/DELETE database.")

    conn.close()
    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n[DA TAO] {OUT}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[LOI] {type(exc).__name__}: {exc}")
        try:
            OUT.write_text(f"[LOI] {type(exc).__name__}: {exc}\n", encoding="utf-8")
        except Exception:
            pass
        raise
