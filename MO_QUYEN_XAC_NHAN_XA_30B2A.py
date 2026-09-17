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
FORM_STATUS = APP / "templates" / "surveys" / "form_status.html"
QUICK_ENTRY = APP / "templates" / "surveys" / "quick_entry.html"

BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "MO_QUYEN_XAC_NHAN_XA_30B2A.txt"

EXPECTED_DB_SHA = "bceddeb34bbb4c6ae3860c6524f8864c9466d4711ae3b89ef2c267bdaa85e4e5"
EXPECTED_SURVEYS_SHA = "5d9cd1dc42577357334f05e57ebaab8f60b6b89e7eacba8615fd3991a0bfcdde"
EXPECTED_FORM_STATUS_SHA = "9a6a76c66334b4ba1332846f294e508e2287c410fd365e53d6cbbd62304e9044"
EXPECTED_QUICK_ENTRY_SHA = "0563611e3700e936761f1d7e1292faf82c73d157950b3e6ca2adc98b622b3f34"

OLD_LINE_RE = re.compile(
    r'(?m)^(?P<indent>[ \t]*)can_confirm_commune = is_admin_role\(role_code\)[ \t]*$'
)
NEW_LINE = (
    'can_confirm_commune = '
    'is_admin_role(role_code) or normalize_role_code(role_code) == "XA"'
)

FORM_OLD_TEXT = "Chỉ tài khoản ADMIN được thay đổi xác nhận cấp xã/phường."
FORM_NEW_TEXT = "Tài khoản Xã và ADMIN được thay đổi xác nhận cấp xã/phường."

QUICK_OLD_TEXT = "Chỉ tài khoản quản trị được thay đổi mục này."
QUICK_NEW_TEXT = "Tài khoản Xã và ADMIN được thay đổi xác nhận cấp xã/phường."


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


def db_check():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_rows = con.execute("PRAGMA foreign_key_check").fetchall()

        summary = con.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status='DA_HOAN_THANH' THEN 1 ELSE 0 END),
                SUM(CASE WHEN household_confirmed_at IS NOT NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN commune_confirmed_at IS NOT NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN commune_confirmed_at IS NULL THEN 1 ELSE 0 END)
            FROM survey_forms
            WHERE survey_batch_id=114
            """
        ).fetchone()
    finally:
        con.close()

    if integrity != "ok":
        raise RuntimeError(f"integrity_check không đạt: {integrity}")
    if fk_rows:
        raise RuntimeError(f"foreign_key_check có {len(fk_rows)} lỗi.")
    return integrity, len(fk_rows), summary


def write_atomic(path: Path, content: str):
    tmp = path.with_name(path.name + ".bai30b2a.tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as out:
        log(out, "=" * 190)
        log(out, "BÀI 30B2A - MỞ QUYỀN XÁC NHẬN PHIẾU CHO TÀI KHOẢN XÃ")
        log(out, "SỬA LỖI BỘ ĐẾM 30B2 - PATCH TỐI THIỂU")
        log(out, "KHÔNG TẠO ROUTE MỚI - KHÔNG GHI DATABASE")
        log(out, "GIỮ NGUYÊN CÁC NGHIỆP VỤ ĐÃ HOÀN THÀNH")
        log(out, "=" * 190)

        for p in (DB, SURVEYS, FORM_STATUS, QUICK_ENTRY):
            if not p.exists():
                raise RuntimeError(f"Không tìm thấy {p}")

        db_sha_before = sha256_file(DB)
        surveys_sha_before = sha256_file(SURVEYS)
        form_sha_before = sha256_file(FORM_STATUS)
        quick_sha_before = sha256_file(QUICK_ENTRY)

        integrity, fk_count, summary_before = db_check()

        log(out, "DB_SHA_BEFORE =", db_sha_before)
        log(out, "SURVEYS_SHA_BEFORE =", surveys_sha_before)
        log(out, "FORM_STATUS_SHA_BEFORE =", form_sha_before)
        log(out, "QUICK_ENTRY_SHA_BEFORE =", quick_sha_before)
        log(out, "INTEGRITY =", integrity)
        log(out, "FK_COUNT =", fk_count)
        log(out, "BATCH114_CONFIRM_SUMMARY =", summary_before)

        if db_sha_before != EXPECTED_DB_SHA:
            raise RuntimeError("DB đã thay đổi sau khảo sát 30B1. Dừng an toàn.")
        if surveys_sha_before != EXPECTED_SURVEYS_SHA:
            raise RuntimeError("surveys.py không còn đúng nền 30B1.")
        if form_sha_before != EXPECTED_FORM_STATUS_SHA:
            raise RuntimeError("form_status.html không còn đúng nền 30B1.")
        if quick_sha_before != EXPECTED_QUICK_ENTRY_SHA:
            raise RuntimeError("quick_entry.html không còn đúng nền 30B1.")

        surveys_text = SURVEYS.read_text(encoding="utf-8-sig")
        form_text = FORM_STATUS.read_text(encoding="utf-8-sig")
        quick_text = QUICK_ENTRY.read_text(encoding="utf-8-sig")

        old_matches = list(OLD_LINE_RE.finditer(surveys_text))
        log(out, "OLD_EXACT_ASSIGN_COUNT_BEFORE =", len(old_matches))
        if len(old_matches) != 4:
            raise RuntimeError(
                f"Cần đúng 4 dòng quyền ADMIN-only; hiện có {len(old_matches)}."
            )

        if surveys_text.count("BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START") != 0:
            raise RuntimeError("Đã tồn tại scope guard 30B2/30B2A. Không cài chồng.")

        if form_text.count(FORM_OLD_TEXT) != 1:
            raise RuntimeError("Chú thích form_status không đúng nền dự kiến.")
        if quick_text.count(QUICK_OLD_TEXT) != 1:
            raise RuntimeError("Chú thích quick_entry không đúng nền dự kiến.")

        # Vá riêng POST cập nhật phiếu bằng block duy nhất, đồng thời thêm guard phạm vi cho XA.
        cap_old = """    nguoi_dung = lay_thong_tin_nguoi_dung(request)
    role_code = str(nguoi_dung.get("role_code") or "")
    can_confirm_commune = is_admin_role(role_code)

    completion_data = b131133_danh_gia_do_day_du_phieu_nhap_nhanh(
"""
        cap_new = """    nguoi_dung = lay_thong_tin_nguoi_dung(request)
    role_code = str(nguoi_dung.get("role_code") or "")
    can_confirm_commune = is_admin_role(role_code) or normalize_role_code(role_code) == "XA"

    # === BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START ===
    # Chỉ bổ sung guard cho vai trò XA vừa được mở quyền.
    # ADMIN và các vai trò cũ giữ nguyên luồng đang chạy.
    if (
        normalize_role_code(role_code) == "XA"
        and not co_quyen_truy_cap_phieu(
            db=db,
            request=request,
            survey_form=survey_form,
        )
    ):
        return RedirectResponse(
            url=f"/dieu-tra/{batch_id}/ho-dan",
            status_code=303,
        )
    # === BAI_30B2_XA_CONFIRM_SCOPE_GUARD_END ===

    completion_data = b131133_danh_gia_do_day_du_phieu_nhap_nhanh(
"""
        if surveys_text.count(cap_old) != 1:
            raise RuntimeError(
                "Không xác định duy nhất block cap_nhat_phieu để cài scope guard."
            )

        surveys_new = surveys_text.replace(cap_old, cap_new, 1)

        # Sau block riêng phải còn chính xác 3 dòng ADMIN-only.
        remaining = list(OLD_LINE_RE.finditer(surveys_new))
        log(out, "OLD_EXACT_ASSIGN_COUNT_AFTER_POST_PATCH =", len(remaining))
        if len(remaining) != 3:
            raise RuntimeError(
                f"Sau vá cap_nhat_phieu phải còn đúng 3 dòng ADMIN-only; hiện có {len(remaining)}."
            )

        # Mở XA ở đúng 3 dòng còn lại.
        surveys_new, replaced = OLD_LINE_RE.subn(
            lambda m: m.group("indent") + NEW_LINE,
            surveys_new,
        )
        log(out, "REMAINING_PERMISSION_LINES_REPLACED =", replaced)
        if replaced != 3:
            raise RuntimeError(f"Phải thay đúng 3 dòng còn lại; đã thay {replaced}.")

        form_new = form_text.replace(FORM_OLD_TEXT, FORM_NEW_TEXT, 1)
        quick_new = quick_text.replace(QUICK_OLD_TEXT, QUICK_NEW_TEXT, 1)

        # Tiền kiểm source sau patch.
        ast.parse(surveys_new)

        exact_old_after = len(list(OLD_LINE_RE.finditer(surveys_new)))
        new_count_after = surveys_new.count(NEW_LINE)

        log(out, "OLD_EXACT_ASSIGN_COUNT_AFTER_ALL_PATCH =", exact_old_after)
        log(out, "NEW_ASSIGN_COUNT_PREWRITE =", new_count_after)

        if exact_old_after != 0:
            raise RuntimeError("Vẫn còn dòng ADMIN-only sau patch.")
        if new_count_after != 4:
            raise RuntimeError(
                f"Phải có đúng 4 dòng quyền ADMIN hoặc XA; hiện có {new_count_after}."
            )
        if surveys_new.count("BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START") != 1:
            raise RuntimeError("Scope guard không đúng 1 block.")
        if form_new.count(FORM_NEW_TEXT) != 1:
            raise RuntimeError("Tiền kiểm form_status thất bại.")
        if quick_new.count(QUICK_NEW_TEXT) != 1:
            raise RuntimeError("Tiền kiểm quick_entry thất bại.")

        # Backup source trước khi ghi.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = BACKUPS / f"source_truoc_BAI30B2A_{stamp}"
        backup_dir.mkdir(parents=True, exist_ok=False)

        backup_map = {
            SURVEYS: backup_dir / "surveys.py",
            FORM_STATUS: backup_dir / "form_status.html",
            QUICK_ENTRY: backup_dir / "quick_entry.html",
        }
        for src, dst in backup_map.items():
            shutil.copy2(src, dst)

        log(out, "SOURCE_BACKUP =", backup_dir)

        wrote = False
        try:
            write_atomic(SURVEYS, surveys_new)
            write_atomic(FORM_STATUS, form_new)
            write_atomic(QUICK_ENTRY, quick_new)
            wrote = True

            py_compile.compile(str(SURVEYS), doraise=True)

            installed_surveys = SURVEYS.read_text(encoding="utf-8-sig")
            installed_form = FORM_STATUS.read_text(encoding="utf-8-sig")
            installed_quick = QUICK_ENTRY.read_text(encoding="utf-8-sig")

            ast.parse(installed_surveys)

            if len(list(OLD_LINE_RE.finditer(installed_surveys))) != 0:
                raise RuntimeError("Hậu kiểm: còn dòng ADMIN-only.")
            if installed_surveys.count(NEW_LINE) != 4:
                raise RuntimeError("Hậu kiểm: quyền ADMIN/XA không đúng 4 vị trí.")
            if installed_surveys.count("BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START") != 1:
                raise RuntimeError("Hậu kiểm: scope guard không đúng.")
            if installed_form.count(FORM_NEW_TEXT) != 1:
                raise RuntimeError("Hậu kiểm form_status không đạt.")
            if installed_quick.count(QUICK_NEW_TEXT) != 1:
                raise RuntimeError("Hậu kiểm quick_entry không đạt.")

            # Database phải không đổi.
            integrity2, fk_count2, summary_after = db_check()
            db_sha_after = sha256_file(DB)

            if db_sha_after != db_sha_before:
                raise RuntimeError("Database thay đổi trong lúc cài source.")
            if integrity2 != "ok" or fk_count2 != 0:
                raise RuntimeError("Database hậu kiểm không đạt.")

            log(out, "PY_COMPILE = PASS")
            log(out, "NEW_ASSIGN_COUNT =", installed_surveys.count(NEW_LINE))
            log(
                out,
                "XA_SCOPE_GUARD_COUNT =",
                installed_surveys.count("BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START"),
            )
            log(out, "FORM_STATUS_PERMISSION_TEXT = PASS")
            log(out, "QUICK_ENTRY_PERMISSION_TEXT = PASS")
            log(out, "BATCH114_CONFIRM_SUMMARY_AFTER =", summary_after)
            log(out, "DB_SHA_AFTER =", db_sha_after)
            log(out, "SURVEYS_SHA_AFTER =", sha256_file(SURVEYS))
            log(out, "FORM_STATUS_SHA_AFTER =", sha256_file(FORM_STATUS))
            log(out, "QUICK_ENTRY_SHA_AFTER =", sha256_file(QUICK_ENTRY))
            log(out, "DATABASE_WRITES_THIS_RUN = 0")
            log(out, "NEW_ROUTE_CREATED = NO")
            log(out, "EXISTING_CONFIRMATION_MECHANISM_REUSED = YES")
            log(out, "BAI30B2A_SUCCESS = YES")
            log(out, "=" * 190)

        except Exception:
            if wrote:
                for target, backup in backup_map.items():
                    shutil.copy2(backup, target)
            raise

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            with OUT.open("a", encoding="utf-8-sig", newline="\n") as out:
                log(out, "")
                log(out, "=" * 190)
                log(out, "BAI30B2A_SUCCESS = NO")
                log(out, "ERROR =", repr(exc))
                if DB.exists():
                    log(out, "DB_SHA_CURRENT =", sha256_file(DB))
                log(out, "DỪNG AN TOÀN.")
                log(out, "=" * 190)
        except Exception:
            print("ERROR =", repr(exc))
        raise
