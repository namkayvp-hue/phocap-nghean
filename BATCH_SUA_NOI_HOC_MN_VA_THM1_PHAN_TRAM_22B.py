# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import py_compile
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
DB = ROOT / "data" / "phocap.db"

YEAR_TEMPLATE = ROOT / "app" / "templates" / "surveys" / "year_records.html"
SURVEYS_ROUTER = ROOT / "app" / "routers" / "surveys.py"
MN_TEMPLATE_ROUTER = ROOT / "app" / "routers" / "pcgdmn_template_report.py"
REPORT_CENTER = ROOT / "app" / "routers" / "report_center.py"

BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
OUT = EXPORT_DIR / "BATCH_SUA_NOI_HOC_MN_VA_THM1_PHAN_TRAM_22B.txt"

EXPECTED_DB_SHA = "2a43e36ff8f192abb46668faa1366ed7242984bfd876f90572cd83b90ee7837e"

MARK_UI = "BATCH22B_SHOW_STUDY_LOCATION_FOR_MN"
MARK_SAVE = "BATCH22_STUDY_LOCATION_SAVE"
MARK_MN_REPORT = "BATCH22_MN01_LOCATION_SCOPE"
MARK_TH_FINAL = "BATCH22B_TH_M1_FINAL_PERCENT_FORMAT"

OLD_OPTION = '                <option\n                    value="DI_HOC_NOI_KHAC"\n                    {% if b1512_location == "DI_HOC_NOI_KHAC" %}selected{% endif %}\n                >\n                    Đi học nơi khác\n                </option>'
NEW_OPTION = '                {# BATCH22_STUDY_LOCATION_SPLIT #}\n                <option\n                    value="DI_HOC_TRONG_TINH"\n                    {% if b1512_location == "DI_HOC_TRONG_TINH" %}selected{% endif %}\n                >\n                    Đi học nơi khác – Trong tỉnh\n                </option>\n\n                <option\n                    value="DI_HOC_NGOAI_TINH"\n                    {% if b1512_location == "DI_HOC_NGOAI_TINH" %}selected{% endif %}\n                >\n                    Đi học nơi khác – Ngoài tỉnh\n                </option>\n\n                <option\n                    value="DI_HOC_NOI_KHAC"\n                    {% if b1512_location == "DI_HOC_NOI_KHAC" %}selected{% endif %}\n                >\n                    Đi học nơi khác – Chưa phân loại (dữ liệu cũ)\n                </option>\n                {# END BATCH22_STUDY_LOCATION_SPLIT #}'
JS_PATCH = '\n<!-- === BATCH22B_SHOW_STUDY_LOCATION_FOR_MN === -->\n<script>\n(function () {\n    "use strict";\n\n    let studyGroup = null;\n    let originalParent = null;\n    let originalNextSibling = null;\n    let scheduled = false;\n\n    function resolveStudyGroup() {\n        if (studyGroup && document.body.contains(studyGroup)) {\n            return studyGroup;\n        }\n\n        const option =\n            document.querySelector(\'option[value="DI_HOC_TRONG_TINH"]\') ||\n            document.querySelector(\'option[value="DI_HOC_NOI_KHAC"]\');\n\n        if (!option) return null;\n\n        const select = option.closest("select");\n        if (!select) return null;\n\n        studyGroup = select.closest(".form-group") || select.parentElement;\n\n        if (studyGroup && !originalParent) {\n            originalParent = studyGroup.parentNode;\n            originalNextSibling = studyGroup.nextSibling;\n        }\n\n        return studyGroup;\n    }\n\n    function preschoolIsActive() {\n        const preschool = document.getElementById(\n            "b131133_preschool_indicators"\n        );\n        if (!preschool) return false;\n\n        return (\n            preschool.offsetParent !== null &&\n            window.getComputedStyle(preschool).display !== "none"\n        );\n    }\n\n    function syncStudyLocation() {\n        scheduled = false;\n\n        const group = resolveStudyGroup();\n        const preschool = document.getElementById(\n            "b131133_preschool_indicators"\n        );\n\n        if (!group || !preschool || !originalParent) return;\n\n        if (preschoolIsActive()) {\n            if (\n                group.parentNode !== preschool.parentNode ||\n                group.nextSibling !== preschool\n            ) {\n                preschool.parentNode.insertBefore(group, preschool);\n            }\n\n            group.style.removeProperty("display");\n            group.hidden = false;\n        } else if (group.parentNode !== originalParent) {\n            if (\n                originalNextSibling &&\n                originalNextSibling.parentNode === originalParent\n            ) {\n                originalParent.insertBefore(group, originalNextSibling);\n            } else {\n                originalParent.appendChild(group);\n            }\n        }\n    }\n\n    function scheduleSync() {\n        if (scheduled) return;\n        scheduled = true;\n        window.setTimeout(syncStudyLocation, 0);\n    }\n\n    document.addEventListener("DOMContentLoaded", function () {\n        scheduleSync();\n        window.setTimeout(scheduleSync, 150);\n        window.setTimeout(scheduleSync, 500);\n\n        document.addEventListener("change", scheduleSync);\n        document.addEventListener("input", scheduleSync);\n\n        const observer = new MutationObserver(scheduleSync);\n        observer.observe(document.body, {\n            attributes: true,\n            childList: true,\n            subtree: true,\n            attributeFilter: ["style", "class", "hidden"]\n        });\n    });\n})();\n</script>\n<!-- === END BATCH22B_SHOW_STUDY_LOCATION_FOR_MN === -->\n'
OLD_WHITELIST = '            if _b1512_location not in {\n                "CHUA_XAC_DINH",\n                "TAI_CHO",\n                "DI_HOC_NOI_KHAC",\n                "NOI_KHAC_DEN",\n            }:'
NEW_WHITELIST = '            # BATCH22_STUDY_LOCATION_SAVE\n            if _b1512_location not in {\n                "CHUA_XAC_DINH",\n                "TAI_CHO",\n                "DI_HOC_TRONG_TINH",\n                "DI_HOC_NGOAI_TINH",\n                "DI_HOC_NOI_KHAC",\n                "NOI_KHAC_DEN",\n            }:'
OLD_MN = '    code = str(row.get("study_location_scope") or "").strip().upper()\n    if code in {"TAI_CHO", "TRONG_XA", "CUNG_XA"}:\n        return True\n    if code in {\n        "KHAC_XA",\n        "TRONG_TINH_KHAC_XA",\n        "NGOAI_DIA_BAN",\n        "TRAI_TUYEN",\n    }:\n        return False'
NEW_MN = '    # BATCH22_MN01_LOCATION_SCOPE\n    # Nơi học khác được phân loại độc lập với biến động cư trú.\n    code = str(row.get("study_location_scope") or "").strip().upper()\n\n    if code == "DI_HOC_TRONG_TINH":\n        return True\n    if code == "DI_HOC_NGOAI_TINH":\n        return False\n\n    if code in {"TAI_CHO", "TRONG_XA", "CUNG_XA"}:\n        return True\n    if code in {\n        "KHAC_XA",\n        "TRONG_TINH_KHAC_XA",\n        "NGOAI_DIA_BAN",\n        "TRAI_TUYEN",\n        "DI_HOC_NOI_KHAC",\n    }:\n        return False'
OLD_FINAL = '    _b15245_apply_primary_th_m1_percentages(ws)\n\n    # Không giữ tên người lập/ký của tệp địa phương mẫu.'
NEW_FINAL = '    _b15245_apply_primary_th_m1_percentages(ws)\n\n    # BATCH22B_TH_M1_FINAL_PERCENT_FORMAT\n    # Giá trị G40:G44 đang là 0..100; chỉ thêm ký hiệu % literal.\n    # Ví dụ 100.0 -> hiển thị 100,00%, không biến thành 10000%.\n    for _percent_ref in ("G40", "G41", "G42", "G43", "G44"):\n        ws[_percent_ref].number_format = r\'0.00\\%\'\n\n    # Không giữ tên người lập/ký của tệp địa phương mẫu.'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def log(f, *parts):
    s = " ".join(str(x) for x in parts)
    print(s)
    f.write(s + "\n")
    f.flush()


def validate_db():
    sha = sha256_file(DB)
    if sha != EXPECTED_DB_SHA:
        raise RuntimeError("DB SHA khác nền đã chốt sau sáp nhập.")

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        year_cols = {
            r[1]
            for r in con.execute(
                'PRAGMA table_info("survey_person_year_records")'
            ).fetchall()
        }
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"Database health không đạt: integrity={integrity}, fk={len(fk)}"
        )

    if "study_location_scope" not in year_cols:
        raise RuntimeError("DB thiếu study_location_scope.")

    return sha, integrity, len(fk)


def backup_files(paths, backup_root):
    result = {}
    for p in paths:
        if not p.exists():
            raise RuntimeError(f"Không tìm thấy source: {p}")
        dst = backup_root / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        result[p] = dst
    return result


def restore_files(backups):
    for p, b in backups.items():
        shutil.copy2(b, p)


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: cần đúng 1 khối, count={count}")
    return text.replace(old, new, 1)


def patch_year_template(text):
    statuses = []

    if 'value="DI_HOC_TRONG_TINH"' not in text or 'value="DI_HOC_NGOAI_TINH"' not in text:
        text = replace_once(text, OLD_OPTION, NEW_OPTION, "year_records split options")
        statuses.append("ADDED_SPLIT_OPTIONS")
    else:
        statuses.append("OPTIONS_ALREADY_PRESENT")

    if MARK_UI not in text:
        if "</body>" not in text:
            raise RuntimeError("year_records.html không có </body>.")
        text = text.replace("</body>", JS_PATCH + "\n</body>", 1)
        statuses.append("SHOW_MN_ADDED")
    else:
        statuses.append("SHOW_MN_ALREADY_PRESENT")

    return text, "+".join(statuses)


def patch_surveys(text):
    if '"DI_HOC_TRONG_TINH"' in text and '"DI_HOC_NGOAI_TINH"' in text:
        return text, "ALREADY_PRESENT"
    return (
        replace_once(
            text, OLD_WHITELIST, NEW_WHITELIST,
            "surveys whitelist"
        ),
        "PATCHED"
    )


def patch_mn_report(text):
    if (
        'code == "DI_HOC_TRONG_TINH"' in text
        and 'code == "DI_HOC_NGOAI_TINH"' in text
    ):
        return text, "ALREADY_PRESENT"
    return (
        replace_once(
            text, OLD_MN, NEW_MN,
            "MN-01 location scope"
        ),
        "PATCHED"
    )


def patch_th_percent(text):
    statuses = []

    # Sửa lỗi bản 22 nếu format đã bị ghi với 2 dấu backslash.
    bad = "number_format = r'0.00\\\\%'"
    good = "number_format = r'0.00\\%'"
    if bad in text:
        text = text.replace(bad, good)
        statuses.append("FIXED_DOUBLE_BACKSLASH")

    # Chốt format ngay trước khi workbook save.
    if MARK_TH_FINAL not in text:
        text = replace_once(
            text, OLD_FINAL, NEW_FINAL,
            "TH-M1 final percent format"
        )
        statuses.append("ADDED_FINAL_FORMAT")
    else:
        statuses.append("FINAL_FORMAT_ALREADY_PRESENT")

    return text, "+".join(statuses)


def verify():
    template = YEAR_TEMPLATE.read_text(encoding="utf-8")
    if 'value="DI_HOC_TRONG_TINH"' not in template:
        raise RuntimeError("Thiếu DI_HOC_TRONG_TINH.")
    if 'value="DI_HOC_NGOAI_TINH"' not in template:
        raise RuntimeError("Thiếu DI_HOC_NGOAI_TINH.")
    if MARK_UI not in template:
        raise RuntimeError("Thiếu UI fix hiện Nơi học cho Mầm non.")

    surveys = SURVEYS_ROUTER.read_text(encoding="utf-8")
    if '"DI_HOC_TRONG_TINH"' not in surveys or '"DI_HOC_NGOAI_TINH"' not in surveys:
        raise RuntimeError("Backend chưa nhận đủ hai mã nơi học.")

    mn = MN_TEMPLATE_ROUTER.read_text(encoding="utf-8")
    if 'code == "DI_HOC_TRONG_TINH"' not in mn:
        raise RuntimeError("MN-01 chưa nhận TRONG_TINH.")
    if 'code == "DI_HOC_NGOAI_TINH"' not in mn:
        raise RuntimeError("MN-01 chưa nhận NGOAI_TINH.")

    report = REPORT_CENTER.read_text(encoding="utf-8")
    if MARK_TH_FINAL not in report:
        raise RuntimeError("Thiếu final format TH-M1.")
    if "number_format = r'0.00\\%'" not in report:
        raise RuntimeError("TH-M1 chưa có format literal % đúng.")


def main():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 160)
        log(f, "BATCH 22B - HIỆN NƠI HỌC CHO MẦM NON + SỬA DẤU % TH-M1")
        log(f, "SOURCE ONLY; KHÔNG GHI DATABASE; KHÔNG ĐỔI DỮ LIỆU CŨ")
        log(f, "=" * 160)

        sha, integrity, fk_count = validate_db()
        log(f, "DB_SHA =", sha)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK =", fk_count)

        paths = [
            YEAR_TEMPLATE,
            SURVEYS_ROUTER,
            MN_TEMPLATE_ROUTER,
            REPORT_CENTER,
        ]

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUP_DIR / f"source_truoc_BATCH22B_{ts}"
        backups = backup_files(paths, backup_root)
        log(f, "SOURCE_BACKUP_DIR =", backup_root)

        try:
            text = YEAR_TEMPLATE.read_text(encoding="utf-8")
            text, status = patch_year_template(text)
            YEAR_TEMPLATE.write_text(text, encoding="utf-8")
            log(f, "PATCH year_records =", status)

            text = SURVEYS_ROUTER.read_text(encoding="utf-8")
            text, status = patch_surveys(text)
            SURVEYS_ROUTER.write_text(text, encoding="utf-8")
            log(f, "PATCH surveys.py =", status)

            text = MN_TEMPLATE_ROUTER.read_text(encoding="utf-8")
            text, status = patch_mn_report(text)
            MN_TEMPLATE_ROUTER.write_text(text, encoding="utf-8")
            log(f, "PATCH MN-01 =", status)

            text = REPORT_CENTER.read_text(encoding="utf-8")
            text, status = patch_th_percent(text)
            REPORT_CENTER.write_text(text, encoding="utf-8")
            log(f, "PATCH TH-M1 =", status)

            for p in (
                SURVEYS_ROUTER,
                MN_TEMPLATE_ROUTER,
                REPORT_CENTER,
            ):
                py_compile.compile(str(p), doraise=True)
            log(f, "PY_COMPILE = PASS")

            verify()
            log(f, "SOURCE_VERIFY = PASS")

        except Exception:
            restore_files(backups)
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        log(f, "DB_SHA_AFTER =", sha256_file(DB))
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "OLD_DATA_MIGRATION = 0")
        log(f, "BATCH_22B_SUCCESS = YES")
        log(f, "")
        log(f, "TEST_1 = Khởi động lại Uvicorn; trẻ Mầm non phải thấy mục Nơi học.")
        log(f, "TEST_2 = Nơi học có Trong tỉnh / Ngoài tỉnh / dữ liệu cũ chưa phân loại.")
        log(f, "TEST_3 = Xuất TH-M1 MỚI; G40:G44 phải hiện ví dụ 100,00%.")
        log(f, "=" * 160)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 160)
                log(f, "BATCH_22B_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 160)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1

    sys.exit(rc)
