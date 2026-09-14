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
QUICK = APP / "templates" / "surveys" / "quick_entry.html"
YEAR = APP / "templates" / "surveys" / "year_records.html"
BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "BO_SUNG_CHU_HO_VA_HOAN_THANH_HO_28C.txt"

PY_MARK = "FIX28C_HEAD_AND_COMPLETION_PREFILL"
QUICK_MARK = "FIX28C_HEAD_PROMPT_UI"
YEAR_MARK = "FIX28C_LAST_PERSON_FINISH_FLAG"


def log(f, *parts):
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def db_precheck():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        current = con.execute(
            "SELECT "
            "(SELECT COUNT(*) FROM survey_people), "
            "(SELECT COUNT(*) FROM survey_person_year_records), "
            "(SELECT COUNT(*) FROM survey_forms)"
        ).fetchone()
    finally:
        con.close()

    if integrity != "ok" or fk:
        raise RuntimeError(
            f"DB health không đạt: integrity={integrity}; FK={len(fk)}"
        )
    return integrity, len(fk), current


def function_span(text: str, name: str) -> tuple[int, int]:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    offsets = [0]
    total = 0
    for line in lines:
        total += len(line)
        offsets.append(total)

    nodes = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError(f"Cần đúng 1 hàm {name}; thực tế={len(nodes)}.")
    node = nodes[0]
    if node.end_lineno is None:
        raise RuntimeError(f"Không xác định được cuối hàm {name}.")
    return offsets[node.lineno - 1], offsets[node.end_lineno]


def get_function(text: str, name: str) -> str:
    a, b = function_span(text, name)
    return text[a:b]


def replace_function(text: str, name: str, fn: str) -> str:
    a, b = function_span(text, name)
    return text[:a] + fn.rstrip() + "\n\n" + text[b:]


def patch_router(source: str):
    fn = get_function(source, "hien_thi_trang_nhap_nhanh")
    if PY_MARK in fn:
        return source, "ALREADY_PRESENT"

    anchor = "    person_summaries: list[dict[str, Any]] = []\n"
    if anchor not in fn:
        raise RuntimeError(
            "Không tìm thấy person_summaries trong hien_thi_trang_nhap_nhanh."
        )

    head_block = (
        f"    # === {PY_MARK}_START ===\n"
        "    _fix28c_head_person = next(\n"
        "        (\n"
        "            item\n"
        "            for item in people\n"
        "            if item.is_active\n"
        "            and la_quan_he_chu_ho(item.relationship_to_head)\n"
        "        ),\n"
        "        None,\n"
        "    )\n"
        "    fix28c_head_missing = bool(\n"
        "        chuan_hoa_van_ban(household.head_name or \"\")\n"
        "        and _fix28c_head_person is None\n"
        "    )\n"
        f"    # === {PY_MARK}_HEAD_END ===\n\n"
    )
    fn = fn.replace(anchor, head_block + anchor, 1)

    # Chèn khối prefill ngay trước TemplateResponse. Khối này hoạt động dù FIX28B
    # đã thay cấu trúc person_form_data hay chưa.
    neutral = "    return templates.TemplateResponse(\n"
    if neutral not in fn:
        raise RuntimeError("Không tìm thấy điểm trước TemplateResponse.")

    prefill = (
        f"    # === {PY_MARK}_PREFILL_START ===\n"
        "    if (\n"
        "        fix28c_head_missing\n"
        "        and not chuan_hoa_van_ban(\n"
        "            str(person_form_data.get(\"full_name\") or \"\")\n"
        "        )\n"
        "    ):\n"
        "        person_form_data[\"full_name\"] = household.head_name\n"
        "        person_form_data[\"relationship_to_head\"] = \"Chủ hộ\"\n\n"
        "    fix28c_ready_to_complete = bool(\n"
        "        active_people_count > 0\n"
        "        and missing_personal_id_count == 0\n"
        "        and missing_year_record_count == 0\n"
        "        and incomplete_year_record_count == 0\n"
        "        and not fix28c_head_missing\n"
        "    )\n\n"
        "    if (\n"
        "        fix28c_ready_to_complete\n"
        "        and survey_form.status != \"DA_HOAN_THANH\"\n"
        "    ):\n"
        "        household_form_data[\"form_status\"] = \"DA_HOAN_THANH\"\n"
        "        if not household_form_data.get(\"survey_date\"):\n"
        "            household_form_data[\"survey_date\"] = date.today().isoformat()\n"
        "        if not chuan_hoa_van_ban(\n"
        "            str(household_form_data.get(\"household_representative_name\") or \"\")\n"
        "        ):\n"
        "            household_form_data[\"household_representative_name\"] = household.head_name\n"
        "        household_form_data[\"household_confirmed\"] = True\n"
        f"    # === {PY_MARK}_PREFILL_END ===\n\n"
    )
    fn = fn.replace(neutral, prefill + neutral, 1)

    context_anchor = '            "person_form_data": person_form_data,\n'
    if context_anchor not in fn:
        raise RuntimeError("Không tìm thấy person_form_data trong context.")
    fn = fn.replace(
        context_anchor,
        context_anchor
        + '            "fix28c_head_missing": fix28c_head_missing,\n'
        + '            "fix28c_ready_to_complete": fix28c_ready_to_complete,\n',
        1,
    )

    return replace_function(source, "hien_thi_trang_nhap_nhanh", fn), "PATCHED"


def remove_html_block(text: str, start: str, end: str) -> str:
    return re.sub(
        re.escape(start) + r".*?" + re.escape(end),
        "",
        text,
        flags=re.S,
    )


def patch_quick_template(text: str):
    start = f"<!-- === {QUICK_MARK}_START === -->"
    end = f"<!-- === {QUICK_MARK}_END === -->"
    text = remove_html_block(text, start, end)

    heading = '<h2 class="section-title">Kiểm tra và nhập năm học</h2>'
    if heading not in text:
        raise RuntimeError("Không tìm thấy tiêu đề 'Kiểm tra và nhập năm học'.")

    banner = (
        heading + "\n"
        + "                    " + start + "\n"
        + "                    {% if fix28c_head_missing %}\n"
        + "                    <div style=\"margin:14px 0 16px;padding:14px 16px;border:1px solid #f2b84b;border-radius:14px;background:#fff8e6;color:#6b4a00;line-height:1.55;\">\n"
        + "                        <strong>👤 Chủ hộ chưa có trong danh sách đối tượng điều tra.</strong><br>\n"
        + "                        Chủ hộ hiện tại: <strong>{{ household.head_name }}</strong>.\n"
        + "                        Hệ thống đã điền sẵn tên và quan hệ <strong>Chủ hộ</strong> ở mục bổ sung bên dưới.\n"
        + "                        Hãy nhập Ngày sinh, Giới tính, Dân tộc và Số định danh nếu có.\n"
        + "                    </div>\n"
        + "                    {% endif %}\n"
        + "                    " + end
    )
    text = text.replace(heading, banner, 1)

    details_pattern = re.compile(r'<details class="add-person"(?P<attrs>[^>]*)>', flags=re.S)
    matches = list(details_pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(
            f"Cần đúng 1 details.add-person; thực tế={len(matches)}."
        )

    whole = matches[0].group(0)
    if "fix28c_head_missing" not in whole:
        attrs = matches[0].group("attrs")
        attrs = re.sub(
            r'\s*\{% if .*?%\}open\{% endif %\}',
            "",
            attrs,
            flags=re.S,
        )
        new = (
            '<details class="add-person"'
            + attrs
            + ' {% if fix28c_head_missing or (thong_bao_loi and person_form_data.full_name) %}open{% endif %}>'
        )
        text = text[:matches[0].start()] + new + text[matches[0].end():]

    summary = "<summary>＋ Thêm nhanh một thành viên</summary>"
    if summary in text:
        text = text.replace(
            summary,
            "<summary>\n"
            "                        {% if fix28c_head_missing %}\n"
            "                            👤 Bổ sung chủ hộ vào đối tượng điều tra\n"
            "                        {% else %}\n"
            "                            ＋ Thêm nhanh một thành viên\n"
            "                        {% endif %}\n"
            "                    </summary>",
            1,
        )

    return text, "PATCHED"


def patch_year_template(text: str):
    start = f"<!-- === {YEAR_MARK}_START === -->"
    end = f"<!-- === {YEAR_MARK}_END === -->"
    text = remove_html_block(text, start, end)

    form_id_pos = text.find('id="year_record_form"')
    if form_id_pos < 0:
        raise RuntimeError("Không tìm thấy year_record_form.")

    form_end = text.find("</form>", form_id_pos)
    if form_end < 0:
        raise RuntimeError("Không xác định được cuối form năm học.")

    block = (
        "\n                " + start + "\n"
        "                {% if nguoi_dung.role_code == 'GIAO_VIEN' and not next_person_url %}\n"
        "                <input type=\"hidden\" name=\"finish_household\" value=\"1\">\n"
        "                {% endif %}\n"
        "                " + end + "\n"
    )
    text = text[:form_end] + block + text[form_end:]
    return text, "PATCHED"


def verify_source(source: str):
    ast.parse(source)
    required = (
        PY_MARK,
        '"fix28c_head_missing": fix28c_head_missing',
        '"fix28c_ready_to_complete": fix28c_ready_to_complete',
        'household_form_data["form_status"] = "DA_HOAN_THANH"',
        'person_form_data["relationship_to_head"] = "Chủ hộ"',
        "BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START",
        "finish_household",
    )
    missing = [x for x in required if x not in source]
    if missing:
        raise RuntimeError("surveys.py sau sửa thiếu: " + repr(missing))


def verify_quick(text: str):
    required = (
        QUICK_MARK,
        "Chủ hộ chưa có trong danh sách đối tượng điều tra",
        "Bổ sung chủ hộ vào đối tượng điều tra",
        "fix28c_head_missing",
    )
    missing = [x for x in required if x not in text]
    if missing:
        raise RuntimeError("quick_entry.html sau sửa thiếu: " + repr(missing))
    from jinja2 import Environment
    Environment().parse(text)


def verify_year(text: str):
    required = (
        YEAR_MARK,
        'name="finish_household"',
        'value="1"',
        "not next_person_url",
    )
    missing = [x for x in required if x not in text]
    if missing:
        raise RuntimeError("year_records.html sau sửa thiếu: " + repr(missing))
    from jinja2 import Environment
    Environment().parse(text)


def clear_cache():
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as f:
        log(f, "=" * 165)
        log(f, "FIX 28C - HIỆN CHỦ HỘ + HOÀN THÀNH HỘ SAU THÀNH VIÊN CUỐI")
        log(f, "SOURCE ONLY - KHÔNG GHI DATABASE TRONG LÚC CÀI")
        log(f, "=" * 165)

        for p in (DB, SURVEYS, QUICK, YEAR):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy: {p}")

        integrity, fk_count, counts = db_precheck()
        db_sha_before = sha256_file(DB)
        log(f, "DB_SHA_BEFORE =", db_sha_before)
        log(f, "INTEGRITY =", integrity)
        log(f, "FK_COUNT =", fk_count)
        log(f, "COUNTS =", {
            "survey_people": int(counts[0] or 0),
            "year_records": int(counts[1] or 0),
            "survey_forms": int(counts[2] or 0),
        })

        source_before = SURVEYS.read_text(encoding="utf-8-sig")
        quick_before = QUICK.read_text(encoding="utf-8-sig")
        year_before = YEAR.read_text(encoding="utf-8-sig")

        # Chỉ cài khi backend hoàn thành hộ V2.3.9 đang tồn tại; không tạo logic trùng.
        for token in (
            "BAI_13B_12_V2_3_9_AUTO_FINISH_HOUSEHOLD_START",
            "finish_household",
            "_b13239_household_completed",
        ):
            if token not in source_before:
                raise RuntimeError(
                    "Backend hoàn thành hộ hiện có không đúng nền; thiếu: " + token
                )

        get_function(source_before, "hien_thi_trang_nhap_nhanh")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_root = BACKUPS / f"source_truoc_FIX28C_{stamp}"
        backups = []
        for src in (SURVEYS, QUICK, YEAR):
            dst = backup_root / src.relative_to(ROOT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            backups.append((src, dst))
        log(f, "SOURCE_BACKUP =", backup_root)

        try:
            source_after, s1 = patch_router(source_before)
            quick_after, s2 = patch_quick_template(quick_before)
            year_after, s3 = patch_year_template(year_before)

            SURVEYS.write_text(source_after, encoding="utf-8")
            QUICK.write_text(quick_after, encoding="utf-8")
            YEAR.write_text(year_after, encoding="utf-8")

            py_compile.compile(str(SURVEYS), doraise=True)
            verify_source(SURVEYS.read_text(encoding="utf-8"))
            verify_quick(QUICK.read_text(encoding="utf-8"))
            verify_year(YEAR.read_text(encoding="utf-8"))
            clear_cache()

            log(f, "PATCH_ROUTER =", s1)
            log(f, "PATCH_QUICK_UI =", s2)
            log(f, "PATCH_LAST_PERSON_FINISH_FLAG =", s3)
            log(f, "PY_COMPILE = PASS")
            log(f, "JINJA_VERIFY = PASS")

        except Exception:
            for src, dst in backups:
                shutil.copy2(dst, src)
            clear_cache()
            log(f, "ROLLBACK_SOURCE = PASS")
            raise

        db_sha_after = sha256_file(DB)
        if db_sha_after != db_sha_before:
            for src, dst in backups:
                shutil.copy2(dst, src)
            clear_cache()
            raise RuntimeError(
                "DB thay đổi trong lúc cài source; source đã rollback."
            )

        log(f, "DB_SHA_AFTER =", db_sha_after)
        log(f, "DATABASE_WRITES_THIS_RUN = 0")
        log(f, "FIX28C_SUCCESS = YES")
        log(f, "")
        log(f, "SAU FIX28C:")
        log(f, " - Thiếu Chủ hộ -> hiện banner ngay trên danh sách + mở sẵn form bổ sung.")
        log(f, " - Form bổ sung được điền sẵn Họ tên + Quan hệ Chủ hộ.")
        log(f, " - Hộ đủ dữ liệu -> màn Nhập nhanh prefill Đã hoàn thành + ngày + người đại diện + xác nhận hộ.")
        log(f, " - GV lưu thành viên cuối -> form luôn gửi finish_household=1; backend hiện có tự chốt hộ nếu đủ điều kiện.")
        log(f, "=" * 165)

    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as f:
                log(f, "")
                log(f, "=" * 165)
                log(f, "FIX28C_SUCCESS = NO")
                log(f, "ERROR =", repr(exc))
                if DB.exists():
                    log(f, "DB_SHA_CURRENT =", sha256_file(DB))
                log(f, "DỪNG AN TOÀN.")
                log(f, "=" * 165)
        except Exception:
            print("ERROR =", repr(exc))
        rc = 1
    raise SystemExit(rc)
