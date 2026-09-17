# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
SURVEYS = APP / "routers" / "surveys.py"
YEAR_TEMPLATE = APP / "templates" / "surveys" / "year_records.html"
QUICK_TEMPLATE = APP / "templates" / "surveys" / "quick_entry.html"

EXPORTS = ROOT / "exports"
OUT = EXPORTS / "KHAO_SAT_TOAN_BO_NGHIEP_VU_NAM_HOC_29.txt"
JSON_OUT = EXPORTS / "KHAO_SAT_TOAN_BO_NGHIEP_VU_NAM_HOC_29.json"

# Các chức năng đã từng có trong dự án và/hoặc backend hiện đã có field.
EXPECTED_FEATURES = {
    "CORE": {
        "learning_status": "Tình trạng học tập",
        "school_id": "Trường hiện tại",
        "class_id": "Lớp hiện tại",
        "school_name_reported": "Tên trường theo phiếu",
        "class_name_reported": "Tên lớp theo phiếu",
    },
    "ATTAINMENT": {
        "highest_completed_grade": "Lớp cao nhất đã hoàn thành",
        "education_attainment_level": "Trình độ học vấn cao nhất",
    },
    "XMC": {
        "is_literacy_target": "Thuộc phạm vi điều tra XMC",
        "literacy_status": "Tình trạng Xóa mù chữ",
        "completed_grade_3": "Hoàn thành lớp 3",
        "completed_grade_5": "Hoàn thành lớp 5",
    },
    "RESIDENCY_EVENTS": {
        "residency_status": "Cư trú",
        "move_in": "Chuyển đến trong năm học",
        "move_in_date": "Ngày chuyển đến",
        "move_in_origin": "Nơi chuyển đến từ",
        "move_out": "Chuyển đi trong năm học",
        "move_out_date": "Ngày chuyển đi",
        "move_out_destination": "Nơi chuyển đi",
        "death": "Tử vong trong năm học",
        "death_date": "Ngày tử vong",
    },
    "STUDY_LOCATION": {
        "study_location_scope": "Nơi học",
        "school_commune_name_reported": "Xã/phường của trường theo phiếu",
        "school_province_name_reported": "Tỉnh/TP của trường theo phiếu",
    },
    "DISABILITY": {
        "disability_status": "Tình trạng khuyết tật",
        "disability_type": "Dạng khuyết tật",
        "disability_level": "Mức độ khuyết tật",
        "disability_certificate": "Giấy xác nhận khuyết tật",
        "inclusive_education": "Giáo dục hòa nhập",
        "disability_support": "Được hỗ trợ",
        "disability_support_details": "Nội dung hỗ trợ",
        "disability_can_learn": "Có khả năng học tập",
        "disability_access_education": "Được tiếp cận giáo dục",
    },
    "MN": {
        "completed_preschool_by_age": "Hoàn thành CT GDMN theo độ tuổi",
        "completed_preschool_5": "Hoàn thành CT GDMN 5 tuổi",
        "attends_two_sessions_per_day": "Học 2 buổi/ngày",
        "prepared_vietnamese": "Trẻ DTTS được chuẩn bị tiếng Việt",
        "attends_required_days": "Đi học đủ ngày",
        "attends_regularly": "Đi học chuyên cần",
        "weight_monitored": "Theo dõi cân nặng",
        "underweight": "Suy dinh dưỡng nhẹ cân",
        "height_monitored": "Theo dõi chiều cao",
        "stunted": "Suy dinh dưỡng thấp còi",
    },
    "TH_THCS": {
        "completed_primary_program": "Hoàn thành chương trình Tiểu học",
        "completed_lower_secondary_program": "Hoàn thành chương trình THCS",
        "post_lower_secondary_path": "Hướng đi sau THCS",
        "is_repeating_grade": "Lưu ban",
        "current_education_program": "Chương trình đang học",
    },
}

IMPORTANT_EXPECTED_VALUES = {
    "LEARNING_STATUS_LABELS": {
        "DANG_HOC": "Đang học",
        "CHUA_DI_HOC": "Chưa đi học",
        "CHUYEN_DEN": "Chuyển đến",
        "CHUYEN_DI": "Chuyển đi",
        "TAM_NGHI": "Tạm nghỉ",
        "THOI_HOC": "Thôi học",
        "BO_HOC": "Bỏ học",
        "DA_TOT_NGHIEP": "Đã tốt nghiệp",
        "KHONG_THUOC_DIEN": "Không thuộc diện theo dõi",
    }
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def line_window(text: str, lineno: int, before: int = 4, after: int = 7) -> str:
    lines = text.splitlines()
    start = max(1, lineno - before)
    end = min(len(lines), lineno + after)
    return "\n".join(
        f"{i:05d}: {lines[i-1]}"
        for i in range(start, end + 1)
    )


def find_python_model_file() -> tuple[Path | None, str]:
    candidates = []
    for p in APP.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "class SurveyPersonYearRecord" in txt:
            candidates.append((p, txt))
    if not candidates:
        return None, ""
    candidates.sort(key=lambda item: len(item[1]))
    return candidates[0]


def function_node(source: str, name: str):
    tree = ast.parse(source)
    nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == name
    ]
    if len(nodes) != 1:
        return None
    return nodes[0]


def ast_signature_params(source: str, node: ast.AST) -> list[str]:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return []
    args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
    return [a.arg for a in args]


def record_assignments(source: str, node: ast.AST) -> list[dict[str, Any]]:
    out = []
    for child in ast.walk(node):
        if not isinstance(child, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            continue
        targets = child.targets if isinstance(child, ast.Assign) else [child.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                if target.value.id in {"record", "form_record", "existing_record"}:
                    out.append({
                        "line": getattr(child, "lineno", None),
                        "base": target.value.id,
                        "field": target.attr,
                        "source": ast.get_source_segment(source, child),
                    })
    return sorted(out, key=lambda x: (x["line"] or 0, x["field"]))


def parse_named_controls(template: str) -> dict[str, list[dict[str, Any]]]:
    controls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pattern = re.compile(
        r'<(?P<tag>input|select|textarea)\b(?P<attrs>[^>]*)>',
        flags=re.I | re.S,
    )
    for m in pattern.finditer(template):
        attrs = m.group("attrs")
        name_m = re.search(r'\bname\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.I)
        id_m = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.I)
        type_m = re.search(r'\btype\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.I)
        if not name_m:
            continue
        name = name_m.group(1)
        line = template[:m.start()].count("\n") + 1
        controls[name].append({
            "tag": m.group("tag").lower(),
            "id": id_m.group(1) if id_m else None,
            "type": type_m.group(1) if type_m else None,
            "line": line,
            "disabled": bool(re.search(r'\bdisabled\b', attrs, flags=re.I)),
            "form": (
                re.search(r'\bform\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.I).group(1)
                if re.search(r'\bform\s*=\s*["\']([^"\']+)["\']', attrs, flags=re.I)
                else None
            ),
            "attrs": re.sub(r'\s+', ' ', attrs).strip()[:500],
        })
    return dict(controls)


def extract_dict_literal(source: str, name: str):
    try:
        tree = ast.parse(source)
    except Exception:
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        value = ast.literal_eval(node.value)
                        return value
                    except Exception:
                        return None
    return None


def model_columns_from_db(con: sqlite3.Connection, table: str) -> list[str]:
    return [str(r[1]) for r in con.execute(f'PRAGMA table_info("{table}")').fetchall()]


def current_year_id(con: sqlite3.Connection) -> int:
    row = con.execute("SELECT id FROM school_years WHERE code='2026-2027' LIMIT 1").fetchone()
    if row:
        return int(row[0])
    return 2


def db_audit(con: sqlite3.Connection) -> dict[str, Any]:
    yid = current_year_id(con)
    result: dict[str, Any] = {"school_year_id": yid}

    result["learning_status_counts"] = [
        [r[0], r[1]]
        for r in con.execute(
            """
            SELECT COALESCE(learning_status,'<NULL>'), COUNT(*)
            FROM survey_person_year_records
            WHERE school_year_id=?
            GROUP BY COALESCE(learning_status,'<NULL>')
            ORDER BY COUNT(*) DESC, 1
            """,
            (yid,),
        ).fetchall()
    ]

    # Một số bất thường nghiệp vụ cần nhìn trước khi sửa.
    q = """
    SELECT
        p.id AS person_id,
        p.full_name,
        p.date_of_birth,
        y.id AS year_record_id,
        y.learning_status,
        y.school_id,
        y.class_id,
        y.school_name_reported,
        y.class_name_reported,
        y.is_literacy_target,
        y.literacy_status,
        y.completed_grade_3,
        y.completed_grade_5,
        y.highest_completed_grade,
        y.education_attainment_level
    FROM survey_people p
    JOIN survey_person_year_records y
      ON y.survey_person_id=p.id
    WHERE y.school_year_id=?
      AND p.is_active=1
    ORDER BY p.id
    """
    rows = con.execute(q, (yid,)).fetchall()
    cols = [d[0] for d in con.execute(q, (yid,)).description]
    people = [dict(zip(cols, r)) for r in rows]

    anomalies = []
    for r in people:
        dob = r.get("date_of_birth")
        age = None
        if dob:
            try:
                year = int(str(dob)[:4])
                age = 2026 - year
            except Exception:
                pass

        no_school = not any([
            r.get("school_id"),
            r.get("class_id"),
            str(r.get("school_name_reported") or "").strip(),
            str(r.get("class_name_reported") or "").strip(),
        ])

        if (
            age is not None
            and age >= 15
            and no_school
            and str(r.get("learning_status") or "").upper() == "DANG_HOC"
        ):
            anomalies.append({
                "type": "AGE15_NO_SCHOOL_BUT_DANG_HOC",
                "person_id": r["person_id"],
                "full_name": r["full_name"],
                "age": age,
                "learning_status": r["learning_status"],
                "literacy_status": r.get("literacy_status"),
                "completed_grade_3": r.get("completed_grade_3"),
                "completed_grade_5": r.get("completed_grade_5"),
            })

        if (
            r.get("is_literacy_target") in (1, True)
            and r.get("completed_grade_3") in (1, True)
            and r.get("completed_grade_5") in (1, True)
            and str(r.get("literacy_status") or "").upper() != "KHONG_THUOC_DIEN"
        ):
            anomalies.append({
                "type": "XMC_COMPLETED_3_5_BUT_STATUS_NOT_KHONG_THUOC_DIEN",
                "person_id": r["person_id"],
                "full_name": r["full_name"],
                "learning_status": r.get("learning_status"),
                "literacy_status": r.get("literacy_status"),
            })

    result["anomalies"] = anomalies[:200]

    test79 = con.execute(
        """
        SELECT
            p.id AS person_id,
            p.full_name,
            p.date_of_birth,
            y.*
        FROM survey_people p
        LEFT JOIN survey_person_year_records y
          ON y.survey_person_id=p.id
         AND y.school_year_id=?
        WHERE p.id=79
        LIMIT 1
        """,
        (yid,),
    )
    row = test79.fetchone()
    if row is not None:
        names = [d[0] for d in test79.description]
        result["person_79"] = dict(zip(names, row))
    else:
        result["person_79"] = None

    # Null / value profile của các field nghiệp vụ.
    cols_year = model_columns_from_db(con, "survey_person_year_records")
    profile_fields = sorted({
        k for group in EXPECTED_FEATURES.values() for k in group.keys()
        if k in cols_year
    })
    profiles = {}
    for field in profile_fields:
        try:
            total, nulls = con.execute(
                f"""
                SELECT COUNT(*),
                       SUM(CASE WHEN "{field}" IS NULL
                                     OR TRIM(CAST("{field}" AS TEXT))=''
                                THEN 1 ELSE 0 END)
                FROM survey_person_year_records
                WHERE school_year_id=?
                """,
                (yid,),
            ).fetchone()
            distinct = con.execute(
                f"""
                SELECT CAST("{field}" AS TEXT), COUNT(*)
                FROM survey_person_year_records
                WHERE school_year_id=?
                GROUP BY CAST("{field}" AS TEXT)
                ORDER BY COUNT(*) DESC
                LIMIT 12
                """,
                (yid,),
            ).fetchall()
            profiles[field] = {
                "total": int(total or 0),
                "blank_or_null": int(nulls or 0),
                "top_values": [[a, b] for a, b in distinct],
            }
        except Exception as exc:
            profiles[field] = {"error": repr(exc)}
    result["field_profiles"] = profiles

    return result


def source_context_hits(source: str, tokens: list[str], max_per_token: int = 6):
    lines = source.splitlines()
    result = {}
    for token in tokens:
        hits = []
        lowtoken = token.lower()
        for i, line in enumerate(lines, start=1):
            if lowtoken in line.lower():
                hits.append({
                    "line": i,
                    "snippet": line_window(source, i, 3, 5),
                })
                if len(hits) >= max_per_token:
                    break
        result[token] = hits
    return result


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 180)
        log(f, "BÀI 29 - KHẢO SÁT TOÀN BỘ NGHIỆP VỤ MÀN THEO DÕI NĂM HỌC")
        log(f, "MỤC TIÊU: TÌM CÁC CHỨC NĂNG BACKEND/MODEL ĐÃ CÓ NHƯNG UI KHÔNG CÒN HIỆN / KHÔNG GỬI / KHÔNG TỰ SUY RA")
        log(f, "CHỈ ĐỌC SOURCE + DATABASE. KHÔNG SỬA SOURCE. KHÔNG GHI DATABASE.")
        log(f, "=" * 180)

        for p in (DB, SURVEYS, YEAR_TEMPLATE):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        db_sha = sha256_file(DB)
        log(f, "DB_SHA =", db_sha)

        con = sqlite3.connect(
            f"file:{DB.as_posix()}?mode=ro",
            uri=True,
            timeout=30,
        )
        try:
            integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
            fk = con.execute("PRAGMA foreign_key_check").fetchall()
            if integrity != "ok" or fk:
                raise RuntimeError(
                    f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
                )

            year_columns = model_columns_from_db(con, "survey_person_year_records")
            dbinfo = db_audit(con)
        finally:
            con.close()

        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", len(fk))
        log(f, "CURRENT_YEAR_ID =", dbinfo["school_year_id"])
        log(f, "LEARNING_STATUS_COUNTS =", dbinfo["learning_status_counts"])
        log(f, "PERSON_79 =", json.dumps(dbinfo["person_79"], ensure_ascii=False, default=str))

        surveys_text = SURVEYS.read_text(encoding="utf-8-sig")
        year_text = YEAR_TEMPLATE.read_text(encoding="utf-8", errors="ignore")
        quick_text = (
            QUICK_TEMPLATE.read_text(encoding="utf-8", errors="ignore")
            if QUICK_TEMPLATE.exists()
            else ""
        )

        node = function_node(surveys_text, "luu_theo_doi_nam_hoc")
        if node is None:
            raise RuntimeError("Không tìm thấy đúng 1 hàm luu_theo_doi_nam_hoc.")

        params = ast_signature_params(surveys_text, node)
        assigns = record_assignments(surveys_text, node)
        assigned_fields = sorted({a["field"] for a in assigns})

        controls = parse_named_controls(year_text)
        control_names = sorted(controls.keys())

        learning_labels = extract_dict_literal(surveys_text, "LEARNING_STATUS_LABELS")
        expected_learning = IMPORTANT_EXPECTED_VALUES["LEARNING_STATUS_LABELS"]

        log(f, "")
        log(f, "=" * 180)
        log(f, "I. KIỂM TRA TÌNH TRẠNG HỌC TẬP / KHÔNG THUỘC DIỆN THEO DÕI")
        log(f, "=" * 180)
        log(f, "LEARNING_STATUS_LABELS_CURRENT =", learning_labels)
        log(
            f,
            "HAS_KHONG_THUOC_DIEN =",
            isinstance(learning_labels, dict)
            and learning_labels.get("KHONG_THUOC_DIEN") == "Không thuộc diện theo dõi",
        )
        log(
            f,
            "TEMPLATE_HAS_learning_status_CONTROL =",
            "learning_status" in controls,
        )
        if "learning_status" in controls:
            log(f, "learning_status_CONTROL =", controls["learning_status"])
        log(
            f,
            "SAVE_PARAM_HAS_learning_status =",
            "learning_status" in params,
        )
        log(
            f,
            "SAVE_ASSIGNS_learning_status =",
            "learning_status" in assigned_fields,
        )

        # Đếm mọi nơi backend ghi learning_status, để phát hiện logic cũ bị mất.
        learning_assign_hits = []
        for i, line in enumerate(surveys_text.splitlines(), start=1):
            if "record.learning_status" in line and "=" in line:
                learning_assign_hits.append({
                    "line": i,
                    "snippet": line_window(surveys_text, i, 4, 8),
                })
        log(f, "ALL_record.learning_status_ASSIGNMENTS =", len(learning_assign_hits))
        for item in learning_assign_hits:
            log(f, "--- learning_status assignment @", item["line"])
            log(f, item["snippet"])

        log(f, "DB_ANOMALIES_COUNT =", len(dbinfo["anomalies"]))
        for item in dbinfo["anomalies"][:50]:
            log(f, "ANOMALY =", json.dumps(item, ensure_ascii=False, default=str))

        log(f, "")
        log(f, "=" * 180)
        log(f, "II. MA TRẬN TOÀN BỘ CHỨC NĂNG: DB ↔ BACKEND PARAM ↔ BACKEND SAVE ↔ UI")
        log(f, "=" * 180)

        matrix = []
        all_expected = []
        for group, fields in EXPECTED_FEATURES.items():
            for field, label in fields.items():
                all_expected.append(field)
                db_field = field in year_columns
                param = field in params
                assigned = field in assigned_fields
                ui = field in controls

                # Event controls không phải cột year-record nhưng phải có UI/param.
                event_virtual = group == "RESIDENCY_EVENTS" and field in {
                    "move_in", "move_in_date", "move_in_origin",
                    "move_out", "move_out_date", "move_out_destination",
                    "death", "death_date",
                    "residency_status",
                }

                status = "OK"
                issues = []
                if db_field and not param:
                    issues.append("DB_CÓ_NHƯNG_POST_KHÔNG_CÓ")
                if db_field and param and not assigned:
                    issues.append("POST_CÓ_NHƯNG_KHÔNG_THẤY_GÁN_RECORD")
                if (db_field or event_virtual) and param and not ui:
                    issues.append("BACKEND_CÓ_NHƯNG_UI_KHÔNG_CÓ_CONTROL")
                if ui and field not in params:
                    issues.append("UI_CÓ_NHƯNG_BACKEND_KHÔNG_NHẬN")
                if issues:
                    status = "CHECK"

                row = {
                    "group": group,
                    "field": field,
                    "label": label,
                    "db": db_field,
                    "param": param,
                    "assigned": assigned,
                    "ui": ui,
                    "status": status,
                    "issues": issues,
                }
                matrix.append(row)

                log(
                    f,
                    f"[{status}] {group:16} {field:38} | "
                    f"DB={int(db_field)} PARAM={int(param)} SAVE={int(assigned)} UI={int(ui)}"
                    + (f" | {','.join(issues)}" if issues else "")
                )

        log(f, "")
        log(f, "=" * 180)
        log(f, "III. CONTROL ĐANG CÓ TRONG year_records.html")
        log(f, "=" * 180)
        for name in control_names:
            entries = controls[name]
            disabled = any(e["disabled"] for e in entries)
            log(
                f,
                f"{name:42} count={len(entries)} disabled_literal={disabled} "
                f"lines={[e['line'] for e in entries]}"
            )

        log(f, "")
        log(f, "=" * 180)
        log(f, "IV. BACKEND PARAM CÓ NHƯNG UI KHÔNG CÓ")
        log(f, "=" * 180)
        backend_business_params = [
            p for p in params
            if p not in {
                "request", "batch_id", "household_id", "person_id",
                "db", "school_year_id", "finish_household",
            }
        ]
        backend_missing_ui = sorted(set(backend_business_params) - set(control_names))
        log(f, "COUNT =", len(backend_missing_ui))
        for p in backend_missing_ui:
            log(f, " -", p)

        log(f, "")
        log(f, "=" * 180)
        log(f, "V. UI CÓ NHƯNG BACKEND KHÔNG NHẬN")
        log(f, "=" * 180)
        ui_missing_backend = sorted(
            set(control_names)
            - set(params)
            - {
                # Các control thuộc endpoint riêng / client-only.
                "q", "page", "page_size",
            }
        )
        log(f, "COUNT =", len(ui_missing_backend))
        for p in ui_missing_backend:
            log(f, " -", p)

        log(f, "")
        log(f, "=" * 180)
        log(f, "VI. CÁC CONTROL BỊ disabled / JS CÓ KHẢ NĂNG ẨN-VÔ HIỆU HÓA")
        log(f, "=" * 180)
        disabled_controls = [
            {"name": n, **e}
            for n, entries in controls.items()
            for e in entries
            if e["disabled"]
        ]
        log(f, "LITERAL_DISABLED_CONTROL_COUNT =", len(disabled_controls))
        for item in disabled_controls:
            log(f, " -", json.dumps(item, ensure_ascii=False))

        js_tokens = [
            ".disabled",
            "style.display",
            "classList.add",
            "hidden",
            "learning_status",
            "literacy_status",
            "is_literacy_target",
            "study_location_scope",
            "disability_status",
            "completed_grade_3",
            "completed_grade_5",
            "highest_completed_grade",
            "education_attainment_level",
        ]
        template_hits = source_context_hits(year_text, js_tokens, max_per_token=12)
        for token, hits in template_hits.items():
            if not hits:
                continue
            log(f, f"--- TOKEN TEMPLATE: {token} | hits={len(hits)}")
            for hit in hits:
                log(f, hit["snippet"])

        log(f, "")
        log(f, "=" * 180)
        log(f, "VII. FIELD PROFILE DB NĂM 2026-2027")
        log(f, "=" * 180)
        for field, profile in dbinfo["field_profiles"].items():
            log(f, field, "=", json.dumps(profile, ensure_ascii=False, default=str))

        log(f, "")
        log(f, "=" * 180)
        log(f, "VIII. MARKER CHỨC NĂNG / DẤU VẾT CÁC BÀI ĐÃ CÀI")
        log(f, "=" * 180)
        markers = sorted(set(re.findall(
            r'(?:BAI_[A-Z0-9_\.]+|FIX[0-9A-Z_]+|GV_MOBILE_[A-Z0-9_]+)',
            surveys_text + "\n" + year_text + "\n" + quick_text,
        )))
        for marker in markers:
            log(f, " -", marker)

        issue_rows = [r for r in matrix if r["issues"]]
        summary = {
            "db_sha": db_sha,
            "integrity": integrity,
            "fk_count": len(fk),
            "current_year_id": dbinfo["school_year_id"],
            "person_79": dbinfo["person_79"],
            "learning_status_labels": learning_labels,
            "learning_status_has_khong_thuoc_dien": (
                isinstance(learning_labels, dict)
                and learning_labels.get("KHONG_THUOC_DIEN")
                == "Không thuộc diện theo dõi"
            ),
            "save_params": params,
            "assigned_fields": assigned_fields,
            "ui_control_names": control_names,
            "matrix": matrix,
            "matrix_issue_count": len(issue_rows),
            "backend_missing_ui": backend_missing_ui,
            "ui_missing_backend": ui_missing_backend,
            "disabled_controls": disabled_controls,
            "learning_status_assignment_hits": learning_assign_hits,
            "db": dbinfo,
            "markers": markers,
            "template_context_hits": template_hits,
        }
        JSON_OUT.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8-sig",
        )

        log(f, "")
        log(f, "=" * 180)
        log(f, "KẾT LUẬN MÁY")
        log(f, "=" * 180)
        log(f, "MATRIX_ISSUE_COUNT =", len(issue_rows))
        log(f, "BACKEND_MISSING_UI_COUNT =", len(backend_missing_ui))
        log(f, "UI_MISSING_BACKEND_COUNT =", len(ui_missing_backend))
        log(f, "DISABLED_CONTROL_COUNT =", len(disabled_controls))
        log(f, "DB_ANOMALY_COUNT =", len(dbinfo["anomalies"]))
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "SOURCE_WRITES_THIS_RUN = 0")
        log(f, "DB_SHA_AFTER_READ_ONLY =", sha256_file(DB))
        log(f, "JSON_OUT =", JSON_OUT)
        log(f, "AUDIT29_SUCCESS = YES")
        log(f, "NEXT = Dùng báo cáo này để làm 1 gói hoàn thiện tổng hợp, không sửa lẻ từng field nữa.")
        log(f, "=" * 180)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 180)
                log(f, "AUDIT29_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 180)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1
    raise SystemExit(rc)
