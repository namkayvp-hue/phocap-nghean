# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
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
APP = ROOT / "app"
DB = ROOT / "data" / "phocap.db"

SURVEYS = APP / "routers" / "surveys.py"
FORM_STATUS = APP / "templates" / "surveys" / "form_status.html"
QUICK_ENTRY = APP / "templates" / "surveys" / "quick_entry.html"

BACKUPS = ROOT / "backups"
EXPORTS = ROOT / "exports"
OUT = EXPORTS / "MO_QUYEN_XAC_NHAN_XA_30B2.txt"

# Khóa đúng nền đã khảo sát ở Bài 30B1.
EXPECTED_DB_SHA = "bceddeb34bbb4c6ae3860c6524f8864c9466d4711ae3b89ef2c267bdaa85e4e5"
EXPECTED_SURVEYS_SHA = "5d9cd1dc42577357334f05e57ebaab8f60b6b89e7eacba8615fd3991a0bfcdde"
EXPECTED_FORM_STATUS_SHA = "9a6a76c66334b4ba1332846f294e508e2287c410fd365e53d6cbbd62304e9044"
EXPECTED_QUICK_ENTRY_SHA = "0563611e3700e936761f1d7e1292faf82c73d157950b3e6ca2adc98b622b3f34"

OLD_ASSIGN = "can_confirm_commune = is_admin_role(role_code)"
NEW_ASSIGN = (
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
    line = " ".join(str(x) for x in parts)
    print(line)
    f.write(line + "\n")
    f.flush()


def db_check():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        fk_rows = con.execute("PRAGMA foreign_key_check").fetchall()

        batch114 = None
        try:
            batch114 = con.execute(
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
        except Exception:
            batch114 = None
    finally:
        con.close()

    if integrity != "ok":
        raise RuntimeError(f"integrity_check không đạt: {integrity}")
    if fk_rows:
        raise RuntimeError(f"foreign_key_check có {len(fk_rows)} lỗi.")
    return integrity, len(fk_rows), batch114


def exact_count(text: str, needle: str, expected: int, label: str):
    n = text.count(needle)
    if n != expected:
        raise RuntimeError(
            f"{label}: cần đúng {expected} lần nhưng tìm thấy {n} lần."
        )
    return n


def main():
    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUPS.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8-sig", newline="\n") as out:
        log(out, "=" * 190)
        log(out, "BÀI 30B2 - MỞ QUYỀN XÁC NHẬN PHIẾU CHO TÀI KHOẢN XÃ")
        log(out, "PATCH TỐI THIỂU - KHÔNG TẠO ROUTE MỚI - KHÔNG GHI DATABASE")
        log(out, "GIỮ NGUYÊN CÁC NGHIỆP VỤ ĐÃ HOÀN THÀNH")
        log(out, "=" * 190)

        for path in (DB, SURVEYS, FORM_STATUS, QUICK_ENTRY):
            if not path.exists():
                raise RuntimeError(f"Không tìm thấy {path}")

        db_sha_before = sha256_file(DB)
        surveys_sha_before = sha256_file(SURVEYS)
        form_sha_before = sha256_file(FORM_STATUS)
        quick_sha_before = sha256_file(QUICK_ENTRY)

        integrity, fk_count, batch114 = db_check()

        log(out, "DB_SHA_BEFORE =", db_sha_before)
        log(out, "SURVEYS_SHA_BEFORE =", surveys_sha_before)
        log(out, "FORM_STATUS_SHA_BEFORE =", form_sha_before)
        log(out, "QUICK_ENTRY_SHA_BEFORE =", quick_sha_before)
        log(out, "INTEGRITY =", integrity)
        log(out, "FK_COUNT =", fk_count)
        log(out, "BATCH114_CONFIRM_SUMMARY =", batch114)

        if db_sha_before != EXPECTED_DB_SHA:
            raise RuntimeError(
                "DB đã thay đổi sau Bài 30B1. Dừng để không sửa trên nền khác."
            )
        if surveys_sha_before != EXPECTED_SURVEYS_SHA:
            raise RuntimeError(
                "surveys.py không còn đúng SHA của Bài 30B1."
            )
        if form_sha_before != EXPECTED_FORM_STATUS_SHA:
            raise RuntimeError(
                "form_status.html không còn đúng SHA của Bài 30B1."
            )
        if quick_sha_before != EXPECTED_QUICK_ENTRY_SHA:
            raise RuntimeError(
                "quick_entry.html không còn đúng SHA của Bài 30B1."
            )

        surveys_text = SURVEYS.read_text(encoding="utf-8-sig")
        form_text = FORM_STATUS.read_text(encoding="utf-8-sig")
        quick_text = QUICK_ENTRY.read_text(encoding="utf-8-sig")

        # Khóa hình dạng nền chính xác.
        exact_count(surveys_text, OLD_ASSIGN, 4, "OLD_ASSIGN")
        exact_count(surveys_text, NEW_ASSIGN, 0, "NEW_ASSIGN trước cài")
        exact_count(form_text, FORM_OLD_TEXT, 1, "FORM_OLD_TEXT")
        exact_count(quick_text, QUICK_OLD_TEXT, 1, "QUICK_OLD_TEXT")

        # Route xác nhận mới tuyệt đối không được tồn tại / không được tạo.
        if "BAI_30B_NEW_ROUTE" in surveys_text:
            raise RuntimeError("Phát hiện dấu hiệu route 30B mới. Dừng an toàn.")

        # 1) Riêng POST cập nhật phiếu: khi mở quyền cho XA, bổ sung guard phạm vi
        #    bằng chính cơ chế co_quyen_truy_cap_phieu đã có của hệ thống.
        cap_marker_old = """    nguoi_dung = lay_thong_tin_nguoi_dung(request)
    role_code = str(nguoi_dung.get("role_code") or "")
    can_confirm_commune = is_admin_role(role_code)

    completion_data = b131133_danh_gia_do_day_du_phieu_nhap_nhanh(
"""
        cap_marker_new = """    nguoi_dung = lay_thong_tin_nguoi_dung(request)
    role_code = str(nguoi_dung.get("role_code") or "")
    can_confirm_commune = is_admin_role(role_code) or normalize_role_code(role_code) == "XA"

    # === BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START ===
    # Chỉ áp dụng thêm cho tài khoản XA vừa được mở quyền xác nhận.
    # ADMIN và các vai trò cũ giữ nguyên luồng đã có.
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
        exact_count(
            surveys_text,
            cap_marker_old,
            1,
            "Block cap_nhat_phieu cần vá phạm vi",
        )
        surveys_new = surveys_text.replace(cap_marker_old, cap_marker_new, 1)

        # 2) Ba vị trí còn lại chỉ mở thêm XA trên đúng cơ chế hiện hữu.
        remaining_old = surveys_new.count(OLD_ASSIGN)
        if remaining_old != 3:
            raise RuntimeError(
                f"Sau khi vá cap_nhat_phieu phải còn đúng 3 OLD_ASSIGN; hiện có {remaining_old}."
            )
        surveys_new = surveys_new.replace(OLD_ASSIGN, NEW_ASSIGN)

        # 3) Chỉ sửa chú thích giao diện cho đúng quyền mới.
        form_new = form_text.replace(FORM_OLD_TEXT, FORM_NEW_TEXT, 1)
        quick_new = quick_text.replace(QUICK_OLD_TEXT, QUICK_NEW_TEXT, 1)

        # Tiền kiểm source mới trước khi chạm file thật.
        ast.parse(surveys_new)
        if surveys_new.count(OLD_ASSIGN) != 0:
            raise RuntimeError("Vẫn còn OLD_ASSIGN sau patch.")
        if surveys_new.count(NEW_ASSIGN) != 4:
            raise RuntimeError("NEW_ASSIGN không đúng 4 vị trí sau patch.")
        if surveys_new.count("BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START") != 1:
            raise RuntimeError("Scope guard 30B2 không đúng 1 block.")
        if FORM_NEW_TEXT not in form_new or FORM_OLD_TEXT in form_new:
            raise RuntimeError("Không chuẩn hóa được chú thích form_status.")
        if QUICK_NEW_TEXT not in quick_new or QUICK_OLD_TEXT in quick_new:
            raise RuntimeError("Không chuẩn hóa được chú thích quick_entry.")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = BACKUPS / f"source_truoc_BAI30B2_{stamp}"
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
            # Ghi atomically từng file qua .tmp rồi replace.
            replacements = (
                (SURVEYS, surveys_new),
                (FORM_STATUS, form_new),
                (QUICK_ENTRY, quick_new),
            )
            for target, content in replacements:
                tmp = target.with_name(target.name + ".bai30b2.tmp")
                tmp.write_text(content, encoding="utf-8", newline="\n")
                tmp.replace(target)
            wrote = True

            # Compile surveys.py sau khi cài.
            py_compile.compile(str(SURVEYS), doraise=True)

            installed_surveys = SURVEYS.read_text(encoding="utf-8-sig")
            installed_form = FORM_STATUS.read_text(encoding="utf-8-sig")
            installed_quick = QUICK_ENTRY.read_text(encoding="utf-8-sig")

            ast.parse(installed_surveys)

            if installed_surveys.count(NEW_ASSIGN) != 4:
                raise RuntimeError("Hậu kiểm: quyền xác nhận XA không đúng 4 vị trí.")
            if installed_surveys.count(OLD_ASSIGN) != 0:
                raise RuntimeError("Hậu kiểm: vẫn còn quyền ADMIN-only.")
            if installed_surveys.count(
                "BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START"
            ) != 1:
                raise RuntimeError("Hậu kiểm: scope guard không đúng 1 block.")
            if installed_form.count(FORM_NEW_TEXT) != 1:
                raise RuntimeError("Hậu kiểm form_status không đạt.")
            if installed_quick.count(QUICK_NEW_TEXT) != 1:
                raise RuntimeError("Hậu kiểm quick_entry không đạt.")

            # DB phải tuyệt đối không đổi trong lúc cài.
            integrity2, fk_count2, batch114_after = db_check()
            db_sha_after = sha256_file(DB)
            if db_sha_after != db_sha_before:
                raise RuntimeError("Database đã thay đổi trong lúc cài source.")
            if integrity2 != "ok" or fk_count2 != 0:
                raise RuntimeError("Database hậu kiểm không đạt.")

            log(out, "PY_COMPILE =", "PASS")
            log(out, "NEW_ASSIGN_COUNT =", installed_surveys.count(NEW_ASSIGN))
            log(
                out,
                "XA_SCOPE_GUARD_COUNT =",
                installed_surveys.count(
                    "BAI_30B2_XA_CONFIRM_SCOPE_GUARD_START"
                ),
            )
            log(out, "FORM_STATUS_PERMISSION_TEXT =", "PASS")
            log(out, "QUICK_ENTRY_PERMISSION_TEXT =", "PASS")
            log(out, "BATCH114_CONFIRM_SUMMARY_AFTER =", batch114_after)
            log(out, "DB_SHA_AFTER =", db_sha_after)
            log(out, "SURVEYS_SHA_AFTER =", sha256_file(SURVEYS))
            log(out, "FORM_STATUS_SHA_AFTER =", sha256_file(FORM_STATUS))
            log(out, "QUICK_ENTRY_SHA_AFTER =", sha256_file(QUICK_ENTRY))
            log(out, "DATABASE_WRITES_THIS_RUN = 0")
            log(out, "NEW_ROUTE_CREATED = NO")
            log(out, "OLD_BUSINESS_ROUTES_CHANGED = NO")
            log(out, "BAI30B2_SUCCESS = YES")
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
                log(out, "BAI30B2_SUCCESS = NO")
                log(out, "ERROR =", repr(exc))
                if DB.exists():
                    log(out, "DB_SHA_CURRENT =", sha256_file(DB))
                log(out, "DỪNG AN TOÀN.")
                log(out, "=" * 190)
        except Exception:
            print("ERROR =", repr(exc))
        raise
