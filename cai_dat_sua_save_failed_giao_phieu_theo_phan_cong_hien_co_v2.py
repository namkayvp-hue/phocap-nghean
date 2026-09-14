# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()

SURVEYS = PROJECT / "app" / "routers" / "surveys.py"
TEMPLATE = PROJECT / "app" / "templates" / "surveys" / "bulk_assignments.html"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = EXPORTS / f"backup_source_sua_save_failed_giao_phieu_v2_{STAMP}"
REPORT = EXPORTS / f"bao_cao_sua_save_failed_giao_phieu_v2_{STAMP}.txt"

V1_HELPER_MARKER = "# === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1_HELPER ==="
V1_POST_MARKER = "# === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1_POST ==="
V1_TEMPLATE_MARKER = "{# === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1 === #}"
V2_MARKER = "# === SUA_SAVE_FAILED_GIAO_PHIEU_THEO_PHAN_CONG_V2 ==="


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="strict")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def db_state() -> dict:
    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        con.execute("PRAGMA query_only = ON")
        return {
            "integrity": str(con.execute("PRAGMA integrity_check").fetchone()[0]),
            "fk_count": len(con.execute("PRAGMA foreign_key_check").fetchall()),
        }
    finally:
        con.close()


def backup_files() -> None:
    for path in (SURVEYS, TEMPLATE):
        dst = BACKUP / path.relative_to(PROJECT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def restore_files() -> None:
    for path in (SURVEYS, TEMPLATE):
        src = BACKUP / path.relative_to(PROJECT)
        if src.exists():
            shutil.copy2(src, path)


def locate_function(source: str, name: str):
    tree = ast.parse(source)
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(nodes) != 1:
        raise RuntimeError(
            f"Cần đúng 1 hàm {name}, tìm thấy {len(nodes)}."
        )
    return nodes[0]


def function_text(source: str, name: str) -> tuple[int, int, str]:
    node = locate_function(source, name)
    lines = source.splitlines(keepends=True)
    start = int(node.lineno) - 1
    end = int(node.end_lineno)
    return start, end, "".join(lines[start:end])


def replace_function(source: str, name: str, new_block: str) -> str:
    start, end, _ = function_text(source, name)
    lines = source.splitlines(keepends=True)
    if not new_block.endswith("\n"):
        new_block += "\n"
    return "".join(lines[:start]) + new_block + "".join(lines[end:])


def patch_post_function(source: str) -> str:
    if V2_MARKER in source:
        return source

    _, _, block = function_text(
        source,
        "luu_phan_cong_v4_theo_cap",
    )

    required_tokens = (
        V1_POST_MARKER,
        "auto_send_existing",
        "auto_targets_by_form",
        'effective_mode = "add"',
        "cap_nhat_phan_cong_v4_mot_phieu(",
    )

    missing = [
        token for token in required_tokens
        if token not in block
    ]

    if missing:
        raise RuntimeError(
            "Hàm POST hiện tại không đúng bản V1 cần sửa. "
            "Thiếu: " + repr(missing)
        )

    old_try_start = block.find("    try:\n")
    if old_try_start < 0:
        raise RuntimeError("Không tìm thấy try ghi dữ liệu.")

    commit_marker = "        db.commit()\n"
    commit_pos = block.find(commit_marker, old_try_start)
    if commit_pos < 0:
        raise RuntimeError("Không tìm thấy db.commit().")

    except_pos = block.find("    except Exception", commit_pos)
    if except_pos < 0:
        raise RuntimeError("Không tìm thấy except Exception.")

    new_write = f'''    try:
        {V2_MARKER}
        # Nếu giao theo phân công hiện có ở cấp Xã -> Trường:
        # gom tất cả tài khoản trường của toàn bộ phiếu đã chọn
        # và đồng bộ nhiệm vụ trường đúng MỘT LẦN.
        if (
            auto_send_existing
            and assignment_level == "school"
        ):
            all_school_account_ids = sorted(
                {{
                    int(user_id)
                    for values in auto_targets_by_form.values()
                    for user_id in values[0]
                }}
            )

            if not all_school_account_ids:
                return RedirectResponse(
                    url=f"{{base_url}}?error=no_existing_assignment",
                    status_code=303,
                )

            dong_bo_nhiem_vu_truong_khi_giao_phieu(
                db=db,
                batch_id=batch.id,
                selected_user_ids=all_school_account_ids,
                actor_user_id=scope["user"].get("id"),
                notes=(
                    assignment_notes
                    or "Giao phiếu theo phân công hiện có."
                ),
            )

        # Luồng chọn nơi nhận mới giữ nguyên.
        elif (
            assignment_level == "school"
            and mode != "clear"
            and not auto_send_existing
        ):
            dong_bo_nhiem_vu_truong_khi_giao_phieu(
                db=db,
                batch_id=batch.id,
                selected_user_ids=selected_ids,
                actor_user_id=scope["user"].get("id"),
                notes=assignment_notes,
            )

        for survey_form in survey_forms:
            effective_ids = selected_ids
            effective_primary_id = primary_user_id
            effective_mode = mode

            if auto_send_existing:
                (
                    effective_ids,
                    effective_primary_id,
                ) = auto_targets_by_form[
                    int(survey_form.id)
                ]

                # Chỉ bổ sung tầng nhận; tuyệt đối không replace
                # để không xóa tổ giáo viên 3 cấp.
                effective_mode = "add"

            cap_nhat_phan_cong_v4_mot_phieu(
                db=db,
                request=request,
                survey_form=survey_form,
                selected_ids=effective_ids,
                primary_user_id=effective_primary_id,
                assignment_notes=(
                    assignment_notes
                    or (
                        "Giao phiếu theo phân công hiện có."
                        if auto_send_existing
                        else ""
                    )
                ),
                mode=effective_mode,
                assignment_level=assignment_level,
            )

        db.commit()
'''

    tail = block[except_pos:]

    old_except = '''    except Exception:
        db.rollback()
        return RedirectResponse(
            url=f"{base_url}?error=save_failed",
            status_code=303,
        )
'''

    new_except = '''    except Exception as exc:
        db.rollback()

        print(
            "[GIAO_PHIEU_SAVE_FAILED] "
            f"{type(exc).__name__}: {exc}"
        )

        return RedirectResponse(
            url=f"{base_url}?error=save_failed",
            status_code=303,
        )
'''

    if old_except in tail:
        tail = tail.replace(old_except, new_except, 1)
    elif "except Exception as exc:" not in tail:
        raise RuntimeError(
            "Không nhận diện được block except hiện tại."
        )

    new_block = block[:old_try_start] + new_write + tail

    return replace_function(
        source,
        "luu_phan_cong_v4_theo_cap",
        new_block,
    )


def verify_source(source: str) -> None:
    ast.parse(source)

    _, _, post = function_text(
        source,
        "luu_phan_cong_v4_theo_cap",
    )

    checks = (
        (V2_MARKER, "marker V2"),
        ("all_school_account_ids = sorted(", "gom toàn bộ trường"),
        (
            "for values in auto_targets_by_form.values()",
            "gom từ tất cả phiếu",
        ),
        ('effective_mode = "add"', "preserve tổ 3 cấp"),
        ("[GIAO_PHIEU_SAVE_FAILED]", "log exception terminal"),
        ("AUTO_SEND_AFTER_TEACHER_ASSIGN_START", "tự báo cáo xã"),
    )

    missing = [
        label for token, label in checks
        if token not in source
    ]

    if missing:
        raise RuntimeError(
            "Kiểm tra source sau sửa không đạt: "
            + ", ".join(missing)
        )

    v2_pos = post.find(V2_MARKER)
    loop_pos = post.find(
        "for survey_form in survey_forms:",
        v2_pos,
    )
    first_sync = post.find(
        "dong_bo_nhiem_vu_truong_khi_giao_phieu(",
        v2_pos,
    )

    if (
        v2_pos < 0
        or loop_pos < 0
        or first_sync < 0
        or first_sync > loop_pos
    ):
        raise RuntimeError(
            "V2 không đặt sync trường trước vòng lặp phiếu."
        )

    loop_body_end = post.find(
        "        db.commit()",
        loop_pos,
    )

    loop_section = post[
        loop_pos:loop_body_end
    ]

    if (
        "dong_bo_nhiem_vu_truong_khi_giao_phieu("
        in loop_section
    ):
        raise RuntimeError(
            "Vẫn còn sync nhiệm vụ trường bên trong vòng lặp phiếu."
        )


def py_compile_surveys() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(SURVEYS),
        ],
        cwd=str(PROJECT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "py_compile lỗi:\n"
            + result.stdout
            + "\n"
            + result.stderr
        )


def jinja_compile() -> None:
    code = (
        "from jinja2 import Environment, FileSystemLoader\n"
        "from pathlib import Path\n"
        f"p=Path(r'{PROJECT}')\n"
        "e=Environment(loader=FileSystemLoader(str(p/'app'/'templates')))\n"
        "e.get_template('surveys/bulk_assignments.html')\n"
        "print('JINJA=OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Jinja lỗi:\n"
            + result.stdout
            + "\n"
            + result.stderr
        )


def main() -> int:
    print("=" * 116)
    print(
        "V2 - SỬA save_failed KHI GIAO PHIẾU "
        "THEO PHÂN CÔNG HIỆN CÓ"
    )
    print("=" * 116)
    print()

    for path in (SURVEYS, TEMPLATE, DB):
        if not path.exists():
            print("[LỖI] Không tìm thấy: " + str(path))
            return 1

    db_sha_before = sha256_file(DB)
    state_before = db_state()

    surveys_before = read_text(SURVEYS)
    template_before = read_text(TEMPLATE)

    try:
        if state_before["integrity"].lower() != "ok":
            raise RuntimeError("integrity_check != ok")

        if state_before["fk_count"] != 0:
            raise RuntimeError("foreign_key_check có lỗi.")

        print("[1/8] Database: integrity=ok; FK=0.")

        if (
            V1_HELPER_MARKER not in surveys_before
            or V1_POST_MARKER not in surveys_before
            or V1_TEMPLATE_MARKER not in template_before
        ):
            raise RuntimeError(
                "Không thấy đầy đủ marker V1. "
                "Dừng để tránh sửa nhầm source."
            )

        ast.parse(surveys_before)

        print(
            "[2/8] Đúng source V1 cần sửa; "
            "AST trước sửa: OK."
        )

        if V2_MARKER in surveys_before:
            print("[3/8] V2 đã có; không cài lặp.")
        else:
            BACKUP.mkdir(
                parents=True,
                exist_ok=False,
            )
            backup_files()
            print(f"[3/8] Backup: {BACKUP}")

            surveys_after = patch_post_function(
                surveys_before
            )
            verify_source(
                surveys_after
            )
            write_text(
                SURVEYS,
                surveys_after,
            )

        final_source = read_text(SURVEYS)
        verify_source(final_source)

        print(
            "[4/8] Đã chuyển sync nhiệm vụ trường "
            "ra ngoài vòng lặp phiếu."
        )

        py_compile_surveys()
        jinja_compile()

        print(
            "[5/8] AST + py_compile + Jinja: ĐẠT."
        )

        print(
            "[6/8] Preserve tổ 3 cấp: "
            "auto delivery vẫn dùng ADD."
        )

        state_after = db_state()
        db_sha_after = sha256_file(DB)

        if state_after != state_before:
            raise RuntimeError(
                "Trạng thái DB trước/sau khác nhau."
            )

        if db_sha_after != db_sha_before:
            raise RuntimeError(
                "SHA256 database thay đổi."
            )

        print(
            "[7/8] Database: KHÔNG THAY ĐỔI."
        )

        report_lines = [
            "=" * 116,
            "BÁO CÁO V2 - SỬA save_failed GIAO PHIẾU",
            "=" * 116,
            "",
            "ĐÃ SỬA:",
            (
                " - Gom toàn bộ school account ID từ các phiếu đã chọn."
            ),
            (
                " - Chỉ gọi dong_bo_nhiem_vu_truong_khi_giao_phieu "
                "1 lần trước vòng lặp."
            ),
            (
                " - Mỗi phiếu vẫn ADD tầng nhận, "
                "không replace tổ 3 cấp."
            ),
            (
                " - Nếu còn lỗi, terminal sẽ in "
                "[GIAO_PHIEU_SAVE_FAILED] <loại lỗi>: <chi tiết>."
            ),
            "",
            f"Backup: {BACKUP if BACKUP.exists() else '(V2 đã có)'}",
            "",
            f"DB SHA trước: {db_sha_before}",
            f"DB SHA sau  : {db_sha_after}",
            "Database: KHÔNG THAY ĐỔI.",
            "",
            "KẾT LUẬN: V2 CÀI ĐẶT THÀNH CÔNG.",
        ]

        EXPORTS.mkdir(
            parents=True,
            exist_ok=True,
        )

        REPORT.write_text(
            "\n".join(report_lines),
            encoding="utf-8-sig",
        )

        print(f"[8/8] Báo cáo: {REPORT}")
        print()
        print("=" * 116)
        print("V2 CÀI ĐẶT THÀNH CÔNG.")
        print("Database: KHÔNG THAY ĐỔI.")
        print("=" * 116)

        return 0

    except Exception as exc:
        print()
        print("=" * 116)
        print("[LỖI] V2 KHÔNG HOÀN TẤT")
        print(str(exc))
        print("=" * 116)

        try:
            if BACKUP.exists():
                restore_files()
                print(
                    "Đã rollback source từ backup V2."
                )
        except Exception as rollback_exc:
            print(
                "Rollback lỗi: "
                + str(rollback_exc)
            )

        try:
            EXPORTS.mkdir(
                parents=True,
                exist_ok=True,
            )
            error_path = (
                EXPORTS
                / f"loi_sua_save_failed_giao_phieu_v2_{STAMP}.txt"
            )
            error_path.write_text(
                f"Lỗi: {exc}\n\n"
                + traceback.format_exc(),
                encoding="utf-8-sig",
            )
            print(
                f"Chi tiết lỗi: {error_path}"
            )
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
