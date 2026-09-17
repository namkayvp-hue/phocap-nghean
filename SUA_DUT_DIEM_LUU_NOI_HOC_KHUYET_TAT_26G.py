# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import py_compile
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = Path(r"C:\PhoCap")
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"
SURVEYS = APP / "routers" / "surveys.py"
TEMPLATE = APP / "templates" / "surveys" / "year_records.html"

BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "SUA_DUT_DIEM_LUU_NOI_HOC_KHUYET_TAT_26G.txt"

ROUTE_START = "# === FIX26G_DIRECT_SAVE_INDICATORS_START ==="
ROUTE_END = "# === FIX26G_DIRECT_SAVE_INDICATORS_END ==="
UI_START = "<!-- === FIX26G_DIRECT_SAVE_INDICATORS_UI_START === -->"
UI_END = "<!-- === FIX26G_DIRECT_SAVE_INDICATORS_UI_END === -->"
MAIN_GUARD = "# === FIX26G_MAIN_SAVE_PRESERVE_START ==="

ROUTE_BLOCK = '\n# === FIX26G_DIRECT_SAVE_INDICATORS_START ===\n@router.post(\n    "/{batch_id}/ho-dan/{household_id}/doi-tuong/{person_id}/nam-hoc/"\n    "luu-chi-bao-nhanh"\n)\ndef fix26g_luu_chi_bao_nhanh(\n    request: Request,\n    batch_id: int,\n    household_id: int,\n    person_id: int,\n    school_year_id: Annotated[int, Form()],\n    study_location_scope: Annotated[str | None, Form()] = None,\n    disability_can_learn: Annotated[str | None, Form()] = None,\n    disability_access_education: Annotated[str | None, Form()] = None,\n    db: Session = Depends(get_db),\n):\n    survey_form = lay_phieu_ho(\n        db=db,\n        batch_id=batch_id,\n        household_id=household_id,\n    )\n    person = lay_doi_tuong_trong_ho(\n        db=db,\n        household_id=household_id,\n        person_id=person_id,\n    )\n\n    if survey_form is None or person is None:\n        return {"ok": False, "message": "Không tìm thấy phiếu hoặc đối tượng."}\n\n    if not co_quyen_truy_cap_phieu(\n        db=db,\n        request=request,\n        survey_form=survey_form,\n    ):\n        return {"ok": False, "message": "Không có quyền cập nhật phiếu."}\n\n    role_code = normalize_role_code(\n        lay_thong_tin_nguoi_dung(request).get("role_code")\n    )\n    if not can_edit_survey_data(role_code):\n        return {"ok": False, "message": "Tài khoản không có quyền cập nhật."}\n\n    if (\n        survey_form.survey_batch.status == "DA_KET_THUC"\n        or survey_form.survey_batch.is_locked\n    ):\n        return {"ok": False, "message": "Đợt điều tra đã khóa/kết thúc."}\n\n    if role_code == TEACHER_ROLE_CODE:\n        school_year_id = int(survey_form.survey_batch.school_year_id)\n\n    record = db.scalar(\n        select(SurveyPersonYearRecord).where(\n            SurveyPersonYearRecord.survey_form_id == survey_form.id,\n            SurveyPersonYearRecord.survey_person_id == person.id,\n            SurveyPersonYearRecord.school_year_id == school_year_id,\n        )\n    )\n    if record is None:\n        return {\n            "ok": False,\n            "message": (\n                "Chưa có bản ghi năm học. Hãy bấm Lưu thông tin năm học "\n                "một lần trước khi lưu riêng chỉ báo."\n            ),\n        }\n\n    allowed_locations = {\n        "CHUA_XAC_DINH",\n        "TAI_CHO",\n        "DI_HOC_TRONG_TINH",\n        "DI_HOC_NGOAI_TINH",\n        "DI_HOC_NOI_KHAC",\n        "NOI_KHAC_DEN",\n    }\n\n    if study_location_scope is not None:\n        location = str(study_location_scope or "").strip().upper()\n        if not location:\n            location = "CHUA_XAC_DINH"\n        if location not in allowed_locations:\n            return {"ok": False, "message": "Giá trị Nơi học không hợp lệ."}\n        record.study_location_scope = location\n\n    def _fix26g_parse_optional_bool(raw_value):\n        if raw_value is None:\n            return "__NO_CHANGE__"\n        raw = str(raw_value or "").strip().upper()\n        if raw == "":\n            return None\n        if raw in {"CO", "1", "TRUE", "YES"}:\n            return True\n        if raw in {"KHONG", "0", "FALSE", "NO"}:\n            return False\n        return "__INVALID__"\n\n    can_learn_value = _fix26g_parse_optional_bool(disability_can_learn)\n    access_value = _fix26g_parse_optional_bool(disability_access_education)\n\n    if can_learn_value == "__INVALID__":\n        return {"ok": False, "message": "Giá trị Có khả năng học tập không hợp lệ."}\n    if access_value == "__INVALID__":\n        return {"ok": False, "message": "Giá trị Tiếp cận giáo dục không hợp lệ."}\n\n    if str(record.disability_status or "").strip().upper() == "CO_KHUYET_TAT":\n        if can_learn_value != "__NO_CHANGE__":\n            record.disability_can_learn = can_learn_value\n        if access_value != "__NO_CHANGE__":\n            record.disability_access_education = access_value\n    else:\n        record.disability_can_learn = None\n        record.disability_access_education = None\n\n    try:\n        db.commit()\n        db.refresh(record)\n    except Exception:\n        db.rollback()\n        return {\n            "ok": False,\n            "message": "Không thể lưu chỉ báo. Dữ liệu cũ được giữ nguyên.",\n        }\n\n    return {\n        "ok": True,\n        "message": "Đã lưu",\n        "study_location_scope": record.study_location_scope,\n        "disability_can_learn": record.disability_can_learn,\n        "disability_access_education": record.disability_access_education,\n    }\n# === FIX26G_DIRECT_SAVE_INDICATORS_END ===\n'
JS_BLOCK = '\n<!-- === FIX26G_DIRECT_SAVE_INDICATORS_UI_START === -->\n<style>\n    #fix26g-save-status {\n        display: none;\n        position: fixed;\n        left: 50%;\n        bottom: 22px;\n        transform: translateX(-50%);\n        z-index: 99999;\n        max-width: 88vw;\n        padding: 10px 16px;\n        border-radius: 999px;\n        background: #166534;\n        color: #fff;\n        font-weight: 800;\n        box-shadow: 0 6px 24px rgba(0,0,0,.18);\n    }\n    #fix26g-save-status.fix26g-error {\n        background: #b42318;\n    }\n</style>\n\n<div id="fix26g-save-status" role="status" aria-live="polite"></div>\n\n<script>\n(function () {\n    "use strict";\n\n    const ids = [\n        "study_location_scope",\n        "disability_can_learn",\n        "disability_access_education"\n    ];\n\n    const saveUrl =\n        "/dieu-tra/{{ batch.id }}/ho-dan/{{ household.id }}/doi-tuong/"\n        + "{{ person.id }}/nam-hoc/luu-chi-bao-nhanh";\n\n    const schoolYearId = "{{ selected_school_year_id }}";\n    let statusTimer = null;\n    let saving = false;\n    let pending = false;\n\n    function field(id) {\n        return document.getElementById(id);\n    }\n\n    function showStatus(message, isError) {\n        const box = document.getElementById("fix26g-save-status");\n        if (!box) return;\n\n        box.textContent = message;\n        box.classList.toggle("fix26g-error", !!isError);\n        box.style.display = "block";\n\n        if (statusTimer) {\n            window.clearTimeout(statusTimer);\n        }\n        statusTimer = window.setTimeout(function () {\n            box.style.display = "none";\n        }, isError ? 5000 : 1800);\n    }\n\n    async function saveIndicators() {\n        if (saving) {\n            pending = true;\n            return;\n        }\n\n        const location = field("study_location_scope");\n        const canLearn = field("disability_can_learn");\n        const access = field("disability_access_education");\n\n        if (!location && !canLearn && !access) return;\n\n        saving = true;\n        pending = false;\n\n        const data = new URLSearchParams();\n        data.set("school_year_id", schoolYearId);\n\n        if (location) {\n            data.set("study_location_scope", location.value || "");\n        }\n        if (canLearn) {\n            data.set("disability_can_learn", canLearn.value || "");\n        }\n        if (access) {\n            data.set("disability_access_education", access.value || "");\n        }\n\n        try {\n            const response = await fetch(saveUrl, {\n                method: "POST",\n                headers: {\n                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"\n                },\n                body: data.toString(),\n                credentials: "same-origin"\n            });\n\n            const result = await response.json();\n\n            if (!response.ok || !result.ok) {\n                showStatus(\n                    (result && result.message)\n                        ? result.message\n                        : "Không lưu được chỉ báo.",\n                    true\n                );\n            } else {\n                showStatus("✓ Đã lưu chỉ báo", false);\n            }\n        } catch (error) {\n            showStatus("Không kết nối được máy chủ để lưu chỉ báo.", true);\n        } finally {\n            saving = false;\n            if (pending) {\n                window.setTimeout(saveIndicators, 50);\n            }\n        }\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        ids.forEach(function (id) {\n            const item = field(id);\n            if (!item) return;\n            item.addEventListener("change", saveIndicators);\n        });\n    });\n})();\n</script>\n<!-- === FIX26G_DIRECT_SAVE_INDICATORS_UI_END === -->\n'
OLD_LOCATION = '        if study_location_scope is not None:\n            _b1512_location = str(\n                study_location_scope or "CHUA_XAC_DINH"\n            ).strip().upper()\n'
NEW_LOCATION = '        # === FIX26G_MAIN_SAVE_PRESERVE_START ===\n        # Nếu control động không gửi giá trị, không được ghi đè dữ liệu\n        # đã được lưu riêng bởi endpoint FIX26G.\n        if (\n            study_location_scope is not None\n            and str(study_location_scope or "").strip()\n        ):\n            _b1512_location = str(\n                study_location_scope\n            ).strip().upper()\n'
OLD_FINAL = '        # === FIX26B_FINAL_ASSIGN_BEFORE_COMMIT ===\n        record.disability_can_learn = disability_can_learn_value\n        record.disability_access_education = disability_access_education_value\n        db.commit()\n'
NEW_FINAL = '        # === FIX26B_FINAL_ASSIGN_BEFORE_COMMIT ===\n        if str(disability_can_learn or "").strip():\n            record.disability_can_learn = disability_can_learn_value\n        if str(disability_access_education or "").strip():\n            record.disability_access_education = disability_access_education_value\n        # === FIX26G_MAIN_SAVE_PRESERVE_END ===\n        db.commit()\n'


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


def db_health():
    con = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
        timeout=30,
    )
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        cols = {
            str(r[1])
            for r in con.execute(
                'PRAGMA table_info("survey_person_year_records")'
            ).fetchall()
        }
    finally:
        con.close()

    required = {
        "study_location_scope",
        "disability_status",
        "disability_can_learn",
        "disability_access_education",
    }
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError("DB thiếu cột: " + repr(missing))

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}, FK={len(fk)}"
        )
    return integrity, len(fk)


def remove_block(text: str, start: str, end: str):
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        flags=re.S,
    )
    return pattern.sub("", text)


def patch_main_save(source: str) -> str:
    if MAIN_GUARD not in source:
        if OLD_LOCATION not in source:
            raise RuntimeError(
                "Không tìm thấy block lưu study_location_scope đúng nền FIX26D."
            )
        source = source.replace(OLD_LOCATION, NEW_LOCATION, 1)

        if OLD_FINAL not in source:
            raise RuntimeError(
                "Không tìm thấy block FIX26B ngay trước db.commit()."
            )
        source = source.replace(OLD_FINAL, NEW_FINAL, 1)

    return source


def verify_source(source: str):
    ast.parse(source)
    for item in (
        ROUTE_START,
        MAIN_GUARD,
        'def fix26g_luu_chi_bao_nhanh(',
        'record.study_location_scope = location',
        'record.disability_can_learn = can_learn_value',
        'record.disability_access_education = access_value',
        'db.refresh(record)',
    ):
        if item not in source:
            raise RuntimeError("surveys.py thiếu: " + item)


def verify_template(text: str):
    for item in (
        UI_START,
        "luu-chi-bao-nhanh",
        'item.addEventListener("change", saveIndicators)',
        'showStatus("✓ Đã lưu chỉ báo", false)',
    ):
        if item not in text:
            raise RuntimeError("year_records.html thiếu: " + item)


def clear_cache():
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 160)
        log(f, "FIX 26G - LƯU ĐỘC LẬP NƠI HỌC + 2 CHỈ BÁO KHUYẾT TẬT")
        log(f, "KHÔNG PHỤ THUỘC FORM NĂM HỌC LỚN; KHÔNG GHI DB KHI CÀI")
        log(f, "=" * 160)

        for p in (DB, SURVEYS, TEMPLATE):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        integrity, fk_count = db_health()
        db_sha_before = sha256_file(DB)

        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)

        source_before = SURVEYS.read_text(encoding="utf-8-sig")
        template_before = TEMPLATE.read_text(encoding="utf-8-sig")

        required_source = (
            "def luu_theo_doi_nam_hoc(",
            "record.study_location_scope = _b1512_location",
            "record.disability_can_learn = disability_can_learn_value",
            "record.disability_access_education = disability_access_education_value",
            "db.commit()",
        )
        missing = [x for x in required_source if x not in source_before]
        if missing:
            raise RuntimeError(
                "surveys.py không còn đúng nền FIX26D: " + repr(missing)
            )

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_FIX26G_{stamp}"
        survey_backup = backup_root / SURVEYS.relative_to(ROOT)
        template_backup = backup_root / TEMPLATE.relative_to(ROOT)

        survey_backup.parent.mkdir(parents=True, exist_ok=False)
        template_backup.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(SURVEYS, survey_backup)
        shutil.copy2(TEMPLATE, template_backup)
        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            source = remove_block(source_before, ROUTE_START, ROUTE_END)
            source = patch_main_save(source)
            source = source.rstrip() + "\n\n" + ROUTE_BLOCK.strip() + "\n"
            SURVEYS.write_text(source, encoding="utf-8")

            template = remove_block(template_before, UI_START, UI_END)
            if "</body>" not in template:
                raise RuntimeError("year_records.html không có </body>.")
            template = template.replace(
                "</body>",
                JS_BLOCK.strip() + "\n</body>",
                1,
            )
            TEMPLATE.write_text(template, encoding="utf-8")

            py_compile.compile(str(SURVEYS), doraise=True)
            verify_source(SURVEYS.read_text(encoding="utf-8"))
            verify_template(TEMPLATE.read_text(encoding="utf-8"))
            clear_cache()

            log(f, "PY_COMPILE = PASS")
            log(f, "SOURCE_VERIFY = PASS")

        except Exception:
            shutil.copy2(survey_backup, SURVEYS)
            shutil.copy2(template_backup, TEMPLATE)
            clear_cache()
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha_before:
            shutil.copy2(survey_backup, SURVEYS)
            shutil.copy2(template_backup, TEMPLATE)
            clear_cache()
            raise RuntimeError(
                "DB thay đổi trong lúc cài source; source đã rollback."
            )

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "FIX26G_SUCCESS = YES")
        log(f, "")
        log(f, "SAU CÀI:")
        log(f, " - Restart Uvicorn + Ctrl+F5.")
        log(f, " - Chọn Nơi học hoặc 2 chỉ báo khuyết tật.")
        log(f, " - Mỗi lần đổi phải hiện toast: ✓ Đã lưu chỉ báo.")
        log(f, " - Sau đó mở lại hồ sơ; lựa chọn phải còn nguyên.")
        log(f, "=" * 160)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 160)
                log(f, "FIX26G_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 160)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    raise SystemExit(rc)
