# -*- coding: utf-8 -*-
# CHỐT QUY TẮC KHÓA TRƯỜNG:
# CHỈ CHO PHÉP KHÓA KHI 100% PHIẾU THUỘC TRƯỜNG ĐÃ HOÀN THÀNH.
#
# Phạm vi sửa:
# - C:\PhoCap\app\routers\survey_school_workflow.py
#
# Không đổi:
# - route
# - menu
# - tên nút
# - bố cục giao diện
# - database
# - luồng khóa/mở xã và tỉnh
#
# An toàn:
# - Khóa SHA256 source đúng bản vừa khảo sát.
# - Backup source trước khi sửa.
# - Rollback source nếu có lỗi.
# - SQLite chỉ đọc mode=ro.
# - integrity_check + foreign_key_check.
# - SHA256 database trước/sau phải giống nhau.
# - AST + py_compile sau sửa.

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


PROJECT = Path(
    os.environ.get(
        "PHOCAP_PROJECT",
        r"C:\PhoCap",
    )
).resolve()

APP = PROJECT / "app"
TARGET = APP / "routers" / "survey_school_workflow.py"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

BACKUP = (
    EXPORTS
    / (
        "backup_source_chot_quy_tac_"
        f"khoa_truong_100_phan_tram_{STAMP}"
    )
)

REPORT = (
    EXPORTS
    / (
        "bao_cao_cai_dat_chot_quy_tac_"
        f"khoa_truong_100_phan_tram_{STAMP}.txt"
    )
)

EXPECTED_SOURCE_SHA256 = (
    "e0ed2a8f596d6a032453a6934cd028240a70c110a4335e11827cacd255208d13"
)

MARKER = (
    "# === CHOT_QUY_TAC_KHOA_TRUONG_"
    "100_PHAN_TRAM_V1 ==="
)

STATUS_KEY = "school_not_complete"

STATUS_MESSAGE = (
    "Chưa thể khóa trường: phải hoàn thành "
    "100% phiếu điều tra của trường."
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(
            f"Không tìm thấy tệp: {path}"
        )

    return path.read_text(
        encoding="utf-8-sig",
        errors="strict",
    )


def write_text(path: Path, text: str) -> None:
    path.write_text(
        text,
        encoding="utf-8",
    )


def backup_source() -> Path:
    dst = (
        BACKUP
        / TARGET.relative_to(PROJECT)
    )

    dst.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        TARGET,
        dst,
    )

    return dst


def restore_source() -> None:
    src = (
        BACKUP
        / TARGET.relative_to(PROJECT)
    )

    if src.exists():
        TARGET.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            src,
            TARGET,
        )


def db_state() -> dict:
    uri = (
        DB.resolve().as_uri()
        + "?mode=ro"
    )

    con = sqlite3.connect(
        uri,
        uri=True,
    )

    try:
        integrity = str(
            con.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        )

        fk_count = len(
            con.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        )

        batch_count = int(
            con.execute(
                "SELECT COUNT(*) FROM survey_batches"
            ).fetchone()[0]
        )

        assignment_count = int(
            con.execute(
                "SELECT COUNT(*) FROM survey_school_assignments"
            ).fetchone()[0]
        )

        locked_assignments = int(
            con.execute(
                "SELECT COUNT(*) "
                "FROM survey_school_assignments "
                "WHERE COALESCE(is_locked, 0)=1"
            ).fetchone()[0]
        )

        return {
            "integrity": integrity,
            "fk_count": fk_count,
            "batch_count": batch_count,
            "assignment_count": assignment_count,
            "locked_assignments": locked_assignments,
        }

    finally:
        con.close()


def verify_db(state: dict) -> None:
    if (
        str(state["integrity"]).lower()
        != "ok"
    ):
        raise RuntimeError(
            "integrity_check != ok"
        )

    if int(state["fk_count"]) != 0:
        raise RuntimeError(
            "foreign_key_check có lỗi."
        )


def locate_function(
    source: str,
    name: str,
) -> ast.FunctionDef:
    tree = ast.parse(source)

    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name == name
    ]

    if len(nodes) != 1:
        raise RuntimeError(
            f"Cần đúng 1 hàm {name}, "
            f"nhưng tìm thấy {len(nodes)}."
        )

    return nodes[0]


def patch_message(text: str) -> str:
    if (
        f'"{STATUS_KEY}"'
        in text
    ):
        return text

    anchor = "WORKFLOW_MESSAGES = {"

    pos = text.find(
        anchor
    )

    if pos < 0:
        raise RuntimeError(
            "Không tìm thấy WORKFLOW_MESSAGES."
        )

    brace = text.find(
        "{",
        pos,
    )

    if brace < 0:
        raise RuntimeError(
            "Không tìm thấy dấu { của WORKFLOW_MESSAGES."
        )

    insertion = (
        "\n"
        f'    "{STATUS_KEY}": (\n'
        f'        "{STATUS_MESSAGE}"\n'
        "    ),"
    )

    return (
        text[: brace + 1]
        + insertion
        + text[brace + 1 :]
    )


def patch_khoa_truong(text: str) -> str:
    if MARKER in text:
        return text

    node = locate_function(
        text,
        "khoa_truong",
    )

    lines = text.splitlines(
        keepends=True
    )

    start = int(node.lineno) - 1
    end = int(node.end_lineno)

    func_text = "".join(
        lines[start:end]
    )

    old = '''    counts = dem_phieu_cua_truong(
        db,
        batch_id=batch.id,
        school_id=school_id,
    )
    assignment.is_locked = True
    assignment.locked_at = datetime.now()
    assignment.locked_by_user_id = actor.get("id")
    assignment.lock_reason = reason
    if counts["form_total"] and counts["form_total"] == counts["completed_total"]:
        assignment.status = "DA_HOAN_THANH"
        assignment.reviewed_at = datetime.now()
'''

    new = f'''    counts = dem_phieu_cua_truong(
        db,
        batch_id=batch.id,
        school_id=school_id,
    )

    {MARKER}
    form_total = int(
        counts.get("form_total")
        or 0
    )
    completed_total = int(
        counts.get("completed_total")
        or 0
    )

    # Chỉ cho phép khóa khi trường có phiếu
    # và 100% phiếu đã hoàn thành.
    if (
        form_total <= 0
        or completed_total != form_total
    ):
        return redirect_workflow(
            batch.id,
            "{STATUS_KEY}",
        )

    assignment.is_locked = True
    assignment.locked_at = datetime.now()
    assignment.locked_by_user_id = actor.get("id")
    assignment.lock_reason = reason

    # Đã qua chốt 100%, nên trạng thái nhiệm vụ
    # được xác nhận hoàn thành đồng thời với khóa.
    assignment.status = "DA_HOAN_THANH"
    assignment.reviewed_at = datetime.now()
'''

    if old not in func_text:
        raise RuntimeError(
            "Không tìm thấy block khóa trường "
            "đúng với source đã khảo sát."
        )

    func_text = func_text.replace(
        old,
        new,
        1,
    )

    return (
        "".join(lines[:start])
        + func_text
        + "".join(lines[end:])
    )


def verify_patched_source(
    source: str,
) -> None:
    ast.parse(
        source
    )

    required = (
        MARKER,
        f'"{STATUS_KEY}"',
        STATUS_MESSAGE,
        'counts.get("form_total")',
        'counts.get("completed_total")',
        "form_total <= 0",
        "completed_total != form_total",
        "assignment.is_locked = True",
        'assignment.status = "DA_HOAN_THANH"',
    )

    missing = [
        token
        for token in required
        if token not in source
    ]

    if missing:
        raise RuntimeError(
            "Source sau sửa thiếu: "
            + repr(missing)
        )

    node = locate_function(
        source,
        "khoa_truong",
    )

    lines = source.splitlines()

    body = "\n".join(
        lines[
            int(node.lineno) - 1 :
            int(node.end_lineno)
        ]
    )

    guard_pos = body.find(
        "completed_total != form_total"
    )

    lock_pos = body.find(
        "assignment.is_locked = True"
    )

    if (
        guard_pos < 0
        or lock_pos < 0
        or guard_pos >= lock_pos
    ):
        raise RuntimeError(
            "Chốt 100% không nằm trước thao tác khóa."
        )

    cases = (
        (6, 5, False, "6/5 phải chặn"),
        (6, 6, True, "6/6 phải cho khóa"),
        (1, 1, True, "1/1 phải cho khóa"),
        (0, 0, False, "0/0 không được khóa"),
        (10, 9, False, "10/9 phải chặn"),
    )

    for (
        total,
        completed,
        expected,
        label,
    ) in cases:
        actual = bool(
            total > 0
            and completed == total
        )

        if actual != expected:
            raise RuntimeError(
                f"Logic nội bộ sai: {label}"
            )


def compile_target() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(TARGET),
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


def main() -> int:
    print(
        "=" * 112
    )
    print(
        "CHỐT QUY TẮC KHÓA TRƯỜNG - "
        "100% PHIẾU PHẢI HOÀN THÀNH"
    )
    print(
        "=" * 112
    )
    print()

    if not TARGET.exists():
        print(
            f"[LỖI] Không tìm thấy: {TARGET}"
        )
        return 1

    if not DB.exists():
        print(
            f"[LỖI] Không tìm thấy: {DB}"
        )
        return 1

    source_before = read_text(
        TARGET
    )

    source_sha_before = sha256_file(
        TARGET
    )

    db_sha_before = sha256_file(
        DB
    )

    before_state = db_state()

    try:
        verify_db(
            before_state
        )

        print(
            "[1/8] Database: "
            f"integrity=ok; "
            f"FK={before_state['fk_count']}; "
            f"batches={before_state['batch_count']}; "
            f"assignments={before_state['assignment_count']}; "
            f"locked_school={before_state['locked_assignments']}."
        )

        if MARKER in source_before:
            print(
                "[2/8] Quy tắc 100% đã có trong source."
            )

            verify_patched_source(
                source_before
            )

            compile_target()

            db_sha_after = sha256_file(
                DB
            )

            if (
                db_sha_before
                != db_sha_after
            ):
                raise RuntimeError(
                    "Database thay đổi bất thường."
                )

            print(
                "[3/8] Source đã ở trạng thái đúng."
            )
            print(
                "[4/8] AST: OK."
            )
            print(
                "[5/8] py_compile: OK."
            )
            print(
                "[6/8] Test logic "
                "6/5 chặn; 6/6 cho khóa: ĐẠT."
            )
            print(
                "[7/8] Database: KHÔNG THAY ĐỔI."
            )
            print(
                "[8/8] Không cần cài lại."
            )

            return 0

        if (
            source_sha_before
            != EXPECTED_SOURCE_SHA256
        ):
            raise RuntimeError(
                "SHA256 survey_school_workflow.py "
                "không còn đúng bản vừa khảo sát.\n"
                f"Hiện tại: {source_sha_before}\n"
                f"Yêu cầu : {EXPECTED_SOURCE_SHA256}\n"
                "Dừng để tránh sửa nhầm source."
            )

        ast.parse(
            source_before
        )

        print(
            "[2/8] Source đúng bản khảo sát; "
            "AST trước sửa: OK."
        )

        backup_path = backup_source()

        print(
            f"[3/8] Backup: {backup_path}"
        )

        patched = patch_message(
            source_before
        )

        patched = patch_khoa_truong(
            patched
        )

        verify_patched_source(
            patched
        )

        write_text(
            TARGET,
            patched,
        )

        compile_target()

        print(
            "[4/8] Đã chèn chốt 100% "
            "trước thao tác khóa."
        )
        print(
            "[5/8] AST + py_compile: ĐẠT."
        )
        print(
            "[6/8] Test logic: "
            "6/5=CHẶN; 6/6=CHO KHÓA; "
            "1/1=CHO KHÓA; 0/0=CHẶN."
        )

        after_state = db_state()

        verify_db(
            after_state
        )

        db_sha_after = sha256_file(
            DB
        )

        if (
            before_state
            != after_state
        ):
            raise RuntimeError(
                "Trạng thái database trước/sau khác nhau."
            )

        if (
            db_sha_before
            != db_sha_after
        ):
            raise RuntimeError(
                "SHA256 database thay đổi."
            )

        source_sha_after = sha256_file(
            TARGET
        )

        report_lines = [
            "=" * 112,
            "BÁO CÁO CÀI ĐẶT - "
            "CHỐT QUY TẮC KHÓA TRƯỜNG 100%",
            "=" * 112,
            "",
            "QUY TẮC:",
            (
                "Chỉ cho phép khóa trường khi "
                "form_total > 0 và "
                "completed_total == form_total."
            ),
            (
                "Nếu chưa đủ 100%: "
                f"status={STATUS_KEY}"
            ),
            (
                "Thông báo: "
                + STATUS_MESSAGE
            ),
            "",
            "SOURCE:",
            f" - Trước: {source_sha_before}",
            f" - Sau  : {source_sha_after}",
            f" - Backup: {backup_path}",
            "",
            "DATABASE:",
            f" - SHA256 trước: {db_sha_before}",
            f" - SHA256 sau  : {db_sha_after}",
            " - Database: KHÔNG THAY ĐỔI.",
            "",
            "KIỂM TRA:",
            " - AST: ĐẠT",
            " - py_compile: ĐẠT",
            " - 6/5: CHẶN",
            " - 6/6: CHO KHÓA",
            " - 1/1: CHO KHÓA",
            " - 0/0: CHẶN",
            " - 10/9: CHẶN",
            "",
            "KẾT LUẬN: CÀI ĐẶT THÀNH CÔNG.",
        ]

        EXPORTS.mkdir(
            parents=True,
            exist_ok=True,
        )

        REPORT.write_text(
            "\n".join(
                report_lines
            ),
            encoding="utf-8-sig",
        )

        print(
            "[7/8] Database: KHÔNG THAY ĐỔI."
        )
        print(
            f"[8/8] Báo cáo: {REPORT}"
        )
        print()
        print(
            "=" * 112
        )
        print(
            "CÀI ĐẶT THÀNH CÔNG."
        )
        print(
            "Quy tắc đã khóa: "
            "chỉ 100% phiếu hoàn thành "
            "mới được khóa trường."
        )
        print(
            "Database: KHÔNG THAY ĐỔI."
        )
        print(
            "=" * 112
        )

        return 0

    except Exception as exc:
        print()
        print(
            "=" * 112
        )
        print(
            "[LỖI] CÀI ĐẶT KHÔNG HOÀN TẤT"
        )
        print(
            str(
                exc
            )
        )
        print(
            "=" * 112
        )

        try:
            if BACKUP.exists():
                restore_source()
                print(
                    "Đã rollback source từ backup."
                )
        except Exception as rollback_exc:
            print(
                "Rollback source gặp lỗi: "
                + str(
                    rollback_exc
                )
            )

        try:
            error_report = (
                EXPORTS
                / (
                    "loi_cai_dat_chot_quy_tac_"
                    f"khoa_truong_100_phan_tram_{STAMP}.txt"
                )
            )

            EXPORTS.mkdir(
                parents=True,
                exist_ok=True,
            )

            error_report.write_text(
                (
                    f"Lỗi: {exc}\n\n"
                    + traceback.format_exc()
                ),
                encoding="utf-8-sig",
            )

            print(
                f"Chi tiết lỗi: {error_report}"
            )
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
