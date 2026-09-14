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
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_source_chan_doan_save_failed_giao_phieu_v2_1_{STAMP}"
REPORT = EXPORTS / f"bao_cao_cai_chan_doan_save_failed_giao_phieu_v2_1_{STAMP}.txt"

V1_MARKER = "# === DONG_BO_GIAO_PHIEU_THEO_PHAN_CONG_HIEN_CO_V1_POST ==="
DIAG_MARKER = "# === CHAN_DOAN_SAVE_FAILED_GIAO_PHIEU_V2_1 ==="


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


def db_health() -> tuple[str, int]:
    uri = DB.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        con.execute("PRAGMA query_only = ON")
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
        return integrity, fk_count
    finally:
        con.close()


def get_function_block(source: str, function_name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Cần đúng 1 hàm {function_name}, tìm thấy {len(matches)}."
        )

    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = node.end_lineno
    return start, end, "".join(lines[start:end])


def replace_function_block(
    source: str,
    function_name: str,
    new_block: str,
) -> str:
    start, end, _ = get_function_block(source, function_name)
    lines = source.splitlines(keepends=True)
    if not new_block.endswith("\n"):
        new_block += "\n"
    return "".join(lines[:start]) + new_block + "".join(lines[end:])


def patch_source(source: str) -> str:
    if DIAG_MARKER in source:
        return source

    _, _, block = get_function_block(
        source,
        "luu_phan_cong_v4_theo_cap",
    )

    if V1_MARKER not in block:
        raise RuntimeError(
            "Không thấy marker V1 trong hàm POST. Dừng để tránh sửa nhầm source."
        )

    old = (
        '        db.commit()\n'
        '    except Exception:\n'
        '        db.rollback()\n'
        '        return RedirectResponse(\n'
        '            url=f"{base_url}?error=save_failed",\n'
        '            status_code=303,\n'
        '        )\n'
    )

    new = (
        '        db.commit()\n'
        '    except Exception as exc:\n'
        f'        {DIAG_MARKER}\n'
        '        db.rollback()\n'
        '\n'
        '        print()\n'
        '        print("=" * 100)\n'
        '        print("[GIAO_PHIEU_SAVE_FAILED]")\n'
        '        print("TYPE :", type(exc).__name__)\n'
        '        print("ERROR:", repr(exc))\n'
        '        print(\n'
        '            "LEVEL:",\n'
        '            assignment_level,\n'
        '            "| MODE:",\n'
        '            mode,\n'
        '            "| AUTO_EXISTING:",\n'
        '            auto_send_existing,\n'
        '        )\n'
        '        print(\n'
        '            "FORM_IDS:",\n'
        '            form_ids,\n'
        '            "| SELECTED_IDS:",\n'
        '            selected_ids,\n'
        '        )\n'
        '        print("=" * 100)\n'
        '        print()\n'
        '\n'
        '        return RedirectResponse(\n'
        '            url=f"{base_url}?error=save_failed",\n'
        '            status_code=303,\n'
        '        )\n'
    )

    count = block.count(old)
    if count != 1:
        raise RuntimeError(
            "Không tìm thấy đúng 1 block transaction cần chẩn đoán; "
            f"tìm thấy {count}."
        )

    new_block = block.replace(old, new, 1)

    result = replace_function_block(
        source,
        "luu_phan_cong_v4_theo_cap",
        new_block,
    )

    ast.parse(result)
    return result


def verify_source(source: str) -> None:
    ast.parse(source)

    _, _, block = get_function_block(
        source,
        "luu_phan_cong_v4_theo_cap",
    )

    required = (
        V1_MARKER,
        DIAG_MARKER,
        "[GIAO_PHIEU_SAVE_FAILED]",
        "TYPE :",
        "ERROR:",
        "auto_send_existing",
        'effective_mode = "add"',
    )

    missing = [
        token for token in required
        if token not in block
    ]

    if missing:
        raise RuntimeError(
            "Source sau cài thiếu: " + repr(missing)
        )


def py_compile_source() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(SURVEYS)],
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


def main() -> int:
    print("=" * 108)
    print("CHẨN ĐOÁN save_failed GIAO PHIẾU - V2.1")
    print("=" * 108)
    print("Chỉ thêm log lỗi runtime; không đổi nghiệp vụ; không sửa DB.")
    print()

    for path in (SURVEYS, DB):
        if not path.exists():
            print("[LỖI] Không tìm thấy: " + str(path))
            return 1

    db_sha_before = sha256_file(DB)
    integrity_before, fk_before = db_health()

    source_before = read_text(SURVEYS)
    source_sha_before = sha256_file(SURVEYS)

    try:
        if integrity_before.lower() != "ok":
            raise RuntimeError("integrity_check != ok")

        if fk_before != 0:
            raise RuntimeError("foreign_key_check có lỗi.")

        print("[1/7] Database: integrity=ok; FK=0.")

        ast.parse(source_before)

        if V1_MARKER not in source_before:
            raise RuntimeError("Source hiện tại không có marker V1.")

        print("[2/7] Source V1 hiện tại: AST OK.")

        if DIAG_MARKER in source_before:
            print("[3/7] Marker chẩn đoán đã có; không cài lặp.")
        else:
            BACKUP.mkdir(parents=True, exist_ok=False)

            backup_path = BACKUP / "app" / "routers" / "surveys.py"
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SURVEYS, backup_path)

            print(f"[3/7] Backup: {backup_path}")

            source_after = patch_source(source_before)

            # Kiểm bản ứng viên hoàn chỉnh trước khi ghi file thật.
            verify_source(source_after)

            write_text(SURVEYS, source_after)

        final_source = read_text(SURVEYS)
        verify_source(final_source)

        print("[4/7] Chỉ bổ sung log exception vào đúng transaction.")

        py_compile_source()
        print("[5/7] AST + py_compile: ĐẠT.")

        integrity_after, fk_after = db_health()
        db_sha_after = sha256_file(DB)

        if (
            integrity_after != integrity_before
            or fk_after != fk_before
            or db_sha_after != db_sha_before
        ):
            raise RuntimeError("Database thay đổi trong quá trình cài.")

        print("[6/7] Database: KHÔNG THAY ĐỔI.")

        source_sha_after = sha256_file(SURVEYS)

        EXPORTS.mkdir(parents=True, exist_ok=True)

        REPORT.write_text(
            "\n".join(
                [
                    "=" * 108,
                    "BÁO CÁO CÀI CHẨN ĐOÁN save_failed GIAO PHIẾU V2.1",
                    "=" * 108,
                    "",
                    "Chỉ thêm log exception runtime.",
                    "Không đổi logic giao phiếu.",
                    "Không đổi template.",
                    "Không đổi database.",
                    "",
                    f"Source SHA trước: {source_sha_before}",
                    f"Source SHA sau  : {source_sha_after}",
                    f"DB SHA trước    : {db_sha_before}",
                    f"DB SHA sau      : {db_sha_after}",
                    "",
                    "Khi tái hiện lỗi, terminal sẽ in:",
                    "[GIAO_PHIEU_SAVE_FAILED]",
                    "TYPE : ...",
                    "ERROR: ...",
                    "LEVEL: ... | MODE: ... | AUTO_EXISTING: ...",
                    "FORM_IDS: ... | SELECTED_IDS: ...",
                ]
            ),
            encoding="utf-8-sig",
        )

        print(f"[7/7] Báo cáo: {REPORT}")
        print()
        print("=" * 108)
        print("CÀI CHẨN ĐOÁN V2.1 THÀNH CÔNG.")
        print("Khởi động Uvicorn và tái hiện đúng thao tác lỗi.")
        print("=" * 108)

        return 0

    except Exception as exc:
        print()
        print("=" * 108)
        print("[LỖI] CÀI CHẨN ĐOÁN V2.1 KHÔNG HOÀN TẤT")
        print(str(exc))
        print("=" * 108)

        try:
            backup_path = BACKUP / "app" / "routers" / "surveys.py"
            if backup_path.exists():
                shutil.copy2(backup_path, SURVEYS)
                print("Đã rollback surveys.py từ backup.")
        except Exception as rollback_exc:
            print("Rollback lỗi: " + str(rollback_exc))

        try:
            EXPORTS.mkdir(parents=True, exist_ok=True)
            error_path = (
                EXPORTS
                / f"loi_cai_chan_doan_save_failed_v2_1_{STAMP}.txt"
            )
            error_path.write_text(
                f"Lỗi: {exc}\n\n" + traceback.format_exc(),
                encoding="utf-8-sig",
            )
            print(f"Chi tiết lỗi: {error_path}")
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
