from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(
    os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")
).resolve()

APP = PROJECT / "app"
ROUTER = APP / "routers" / "survey_batch_admin_v13b11.py"
TEMPLATE = (
    APP
    / "templates"
    / "surveys"
    / "province_batch_admin_v13b11.html"
)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = (
    PROJECT
    / "exports"
    / f"backup_source_bai_13b_11_3_{STAMP}"
)

ROUTER_MARK = "BAI_13B_11_3_BULK_DELETE_START"
PANEL_MARK = "BAI_13B_11_3_BULK_PANEL_START"
SCRIPT_MARK = "BAI_13B_11_3_BULK_SCRIPT_START"

ROUTER_BLOCK = '\n# === BAI_13B_11_3_BULK_DELETE_START ===\n\nBULK_DELETE_CONFIRM_TEXT = "XOA TOAN BO DA CHON"\n\n\n@router.post("/xoa-hang-loat")\nasync def delete_empty_batches_bulk(request: Request):\n    """\n    Xóa nhiều đợt trống trong MỘT giao dịch:\n    1) kiểm tra sơ bộ tất cả đợt;\n    2) tạo một backup SQLite đầy đủ;\n    3) BEGIN IMMEDIATE và kiểm tra lại từng đợt;\n    4) chỉ khi toàn bộ vẫn an toàn mới DELETE;\n    5) nếu một đợt không đạt -> rollback toàn bộ.\n    """\n    if not _admin(request):\n        return _forbidden()\n\n    form = await request.form()\n    actor = _user(request)\n\n    raw_ids = list(form.getlist("batch_ids"))\n    batch_ids: list[int] = []\n    for raw in raw_ids:\n        try:\n            value = int(str(raw).strip())\n        except (TypeError, ValueError):\n            continue\n        if value > 0:\n            batch_ids.append(value)\n\n    batch_ids = sorted(set(batch_ids))\n\n    try:\n        selected_year_id = int(str(form.get("school_year_id") or "0").strip())\n    except (TypeError, ValueError):\n        selected_year_id = 0\n\n    confirm_phrase = _clean(form.get("confirm_phrase"), 200)\n\n    def redirect_blocked(detail: str, backup: str = ""):\n        q = {\n            "status": "delete_blocked",\n            "detail": detail,\n        }\n        if selected_year_id > 0:\n            q["school_year_id"] = selected_year_id\n        if backup:\n            q["backup"] = backup\n        return RedirectResponse(\n            url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q),\n            status_code=303,\n        )\n\n    def redirect_failed(backup: str = ""):\n        q = {"status": "delete_failed"}\n        if selected_year_id > 0:\n            q["school_year_id"] = selected_year_id\n        if backup:\n            q["backup"] = backup\n        return RedirectResponse(\n            url="/dieu-tra/quan-ly-dot-toan-tinh?" + urlencode(q),\n            status_code=303,\n        )\n\n    if not batch_ids:\n        return redirect_blocked(\n            "Chưa chọn đợt nào để xóa hàng loạt."\n        )\n\n    if len(batch_ids) > 1000:\n        return redirect_blocked(\n            "Số đợt được chọn vượt giới hạn an toàn 1000 đợt."\n        )\n\n    if confirm_phrase != BULK_DELETE_CONFIRM_TEXT:\n        return redirect_blocked(\n            f\'Phải nhập chính xác: "{BULK_DELETE_CONFIRM_TEXT}".\'\n        )\n\n    snapshots: list[dict[str, Any]] = []\n    first_year_id: int | None = None\n\n    # -----------------------------------------------------\n    # LẦN KIỂM TRA 1 - chỉ đọc, trước khi tạo backup\n    # -----------------------------------------------------\n    con = sqlite3.connect(str(DATABASE_PATH), timeout=30)\n    try:\n        con.execute("PRAGMA foreign_keys=ON")\n        con.execute("PRAGMA busy_timeout=30000")\n\n        for batch_id in batch_ids:\n            snapshot = _snapshot(con, batch_id)\n            if snapshot is None:\n                return redirect_blocked(\n                    f"Không tìm thấy đợt ID {batch_id}; chưa xóa đợt nào."\n                )\n\n            year_id = int(snapshot.get("school_year_id") or 0)\n            if first_year_id is None:\n                first_year_id = year_id\n\n            if year_id != first_year_id:\n                return redirect_blocked(\n                    "Các đợt được chọn không cùng một năm học; "\n                    "chưa xóa đợt nào."\n                )\n\n            if selected_year_id > 0 and year_id != selected_year_id:\n                return redirect_blocked(\n                    "Có đợt không thuộc năm học đang hiển thị; "\n                    "chưa xóa đợt nào."\n                )\n\n            reason = _safety_reason(\n                snapshot,\n                _references(con, batch_id),\n            )\n            if reason:\n                return redirect_blocked(\n                    f"Đợt {snapshot.get(\'code\')}: {reason} "\n                    "Toàn bộ thao tác đã dừng, chưa xóa đợt nào."\n                )\n\n            snapshots.append(snapshot)\n    finally:\n        con.close()\n\n    if first_year_id and selected_year_id <= 0:\n        selected_year_id = first_year_id\n\n    # -----------------------------------------------------\n    # MỘT BACKUP CHUNG CHO TOÀN BỘ LẦN XÓA\n    # -----------------------------------------------------\n    bulk_snapshot = {\n        "code": (\n            f"HANG_LOAT_{len(batch_ids)}_DOT_"\n            f"NAM_{selected_year_id or \'KHONG_RO\'}"\n        ),\n        "name": "Bài 13B-11.3 - Xóa hàng loạt đợt trống",\n        "status": "CHUAN_BI",\n        "school_year_id": selected_year_id or first_year_id,\n        "batch_ids": batch_ids,\n        "batch_codes": [\n            str(item.get("code") or "")\n            for item in snapshots\n        ],\n        "batch_total": len(batch_ids),\n    }\n\n    try:\n        backup_dir = _backup_before_delete(\n            actor,\n            bulk_snapshot,\n        )\n    except Exception:\n        return redirect_failed()\n\n    # -----------------------------------------------------\n    # LẦN KIỂM TRA 2 - trong giao dịch ghi ngay trước DELETE\n    # -----------------------------------------------------\n    write_con = sqlite3.connect(str(DATABASE_PATH), timeout=30)\n    deleted_total = 0\n    try:\n        write_con.execute("PRAGMA foreign_keys=ON")\n        write_con.execute("PRAGMA busy_timeout=30000")\n        write_con.execute("BEGIN IMMEDIATE")\n\n        for batch_id in batch_ids:\n            latest = _snapshot(write_con, batch_id)\n\n            latest_reason = _safety_reason(\n                latest,\n                _references(write_con, batch_id),\n            )\n\n            if latest_reason:\n                raise RuntimeError(\n                    "Dữ liệu đã thay đổi sau bước kiểm tra ban đầu. "\n                    f"Đợt ID {batch_id}: {latest_reason}"\n                )\n\n            latest_year_id = int(\n                (latest or {}).get("school_year_id") or 0\n            )\n            if (\n                selected_year_id > 0\n                and latest_year_id != selected_year_id\n            ):\n                raise RuntimeError(\n                    "Phát hiện đợt thay đổi phạm vi năm học "\n                    "trong lúc thực hiện."\n                )\n\n        # Chỉ sau khi TẤT CẢ đều vượt qua lần kiểm tra 2\n        # mới bắt đầu DELETE.\n        for batch_id in batch_ids:\n            cursor = write_con.execute(\n                "DELETE FROM survey_batches WHERE id=?",\n                (batch_id,),\n            )\n            if int(cursor.rowcount or 0) != 1:\n                raise RuntimeError(\n                    f"Không xóa đúng một bản ghi cho đợt ID {batch_id}."\n                )\n            deleted_total += 1\n\n        if deleted_total != len(batch_ids):\n            raise RuntimeError(\n                "Số đợt đã xóa không khớp số đợt được chọn."\n            )\n\n        write_con.commit()\n\n    except Exception as exc:\n        write_con.rollback()\n        return redirect_blocked(\n            "Xóa hàng loạt không thực hiện vì kiểm tra an toàn "\n            f"không đạt: {str(exc)[:500]}",\n            backup=backup_dir.name,\n        )\n\n    finally:\n        write_con.close()\n\n    # Nhật ký sau commit. Nếu ghi log phụ thất bại thì không làm\n    # thay đổi kết quả giao dịch đã hoàn tất.\n    try:\n        for snapshot in snapshots:\n            _log_delete(\n                actor,\n                snapshot,\n                backup_dir,\n            )\n    except Exception:\n        pass\n\n    q = {\n        "status": "batch_deleted",\n        "code": f"{deleted_total} đợt trống đã chọn",\n        "backup": backup_dir.name,\n    }\n    if selected_year_id > 0:\n        q["school_year_id"] = selected_year_id\n\n    return RedirectResponse(\n        url="/dieu-tra/quan-ly-dot-toan-tinh?"\n        + urlencode(q),\n        status_code=303,\n    )\n\n\n# === BAI_13B_11_3_BULK_DELETE_END ===\n'
BULK_PANEL = '\n            {# === BAI_13B_11_3_BULK_PANEL_START === #}\n            <form\n                id="b1311-bulk-delete-form"\n                method="post"\n                action="/dieu-tra/quan-ly-dot-toan-tinh/xoa-hang-loat"\n                style="\n                    margin: 0 0 14px;\n                    padding: 14px;\n                    border: 1px solid #efb7b2;\n                    border-radius: 10px;\n                    background: #fff6f5;\n                "\n            >\n                <input\n                    type="hidden"\n                    name="school_year_id"\n                    value="{{ selected_year_id or \'\' }}"\n                >\n\n                <div id="b1311-bulk-id-container"></div>\n\n                <div\n                    style="\n                        display: grid;\n                        grid-template-columns: minmax(260px, 1fr) auto;\n                        gap: 10px;\n                        align-items: end;\n                    "\n                >\n                    <div>\n                        <label\n                            for="b1311-bulk-confirm-phrase"\n                            style="\n                                display:block;\n                                margin-bottom:6px;\n                                font-weight:700;\n                            "\n                        >\n                            Xác nhận xóa toàn bộ các đợt đã chọn\n                        </label>\n                        <input\n                            id="b1311-bulk-confirm-phrase"\n                            class="b1311-control"\n                            type="text"\n                            name="confirm_phrase"\n                            autocomplete="off"\n                            placeholder="XOA TOAN BO DA CHON"\n                            required\n                        >\n                        <div\n                            id="b1311-bulk-delete-help"\n                            style="\n                                margin-top:6px;\n                                color:#7a4a45;\n                                font-size:13px;\n                                line-height:1.5;\n                            "\n                        >\n                            Chưa chọn đợt nào.\n                            Hệ thống chỉ xóa khi toàn bộ đợt được chọn đều\n                            vượt qua kiểm tra an toàn.\n                        </div>\n                    </div>\n\n                    <button\n                        id="b1311-bulk-delete-button"\n                        class="b1311-danger-button"\n                        type="submit"\n                        disabled\n                        style="\n                            min-height:46px;\n                            padding-left:18px;\n                            padding-right:18px;\n                        "\n                    >\n                        🗑 Xóa toàn bộ đã chọn\n                    </button>\n                </div>\n            </form>\n            {# === BAI_13B_11_3_BULK_PANEL_END === #}\n'
BULK_SCRIPT = '\n    {# === BAI_13B_11_3_BULK_SCRIPT_START === #}\n    <script>\n    (function () {\n        const bulkForm =\n            document.getElementById("b1311-bulk-delete-form");\n        const bulkButton =\n            document.getElementById("b1311-bulk-delete-button");\n        const bulkHelp =\n            document.getElementById("b1311-bulk-delete-help");\n        const idContainer =\n            document.getElementById("b1311-bulk-id-container");\n\n        if (!bulkForm || !bulkButton || !idContainer) {\n            return;\n        }\n\n        function selectedBoxes() {\n            return Array.from(\n                document.querySelectorAll(\n                    \'.b1311-delete-form \' +\n                    \'input[name="confirm_checked"]:checked\'\n                )\n            ).filter(function (box) {\n                return !box.disabled;\n            });\n        }\n\n        function selectedIds() {\n            const ids = [];\n\n            selectedBoxes().forEach(function (box) {\n                let value = box.getAttribute("data-batch-id");\n\n                if (!value) {\n                    const ownForm = box.closest("form");\n                    const action = ownForm\n                        ? String(ownForm.getAttribute("action") || "")\n                        : "";\n                    const match = action.match(/\\/(\\d+)\\/xoa$/);\n                    if (match) {\n                        value = match[1];\n                    }\n                }\n\n                const numberValue = Number(value);\n                if (\n                    Number.isInteger(numberValue) &&\n                    numberValue > 0 &&\n                    !ids.includes(numberValue)\n                ) {\n                    ids.push(numberValue);\n                }\n            });\n\n            ids.sort(function (a, b) {\n                return a - b;\n            });\n\n            return ids;\n        }\n\n        function refreshBulkDelete() {\n            const ids = selectedIds();\n            const total = ids.length;\n\n            bulkButton.disabled = total === 0;\n            bulkButton.textContent = total > 0\n                ? "🗑 Xóa toàn bộ đã chọn (" + total + ")"\n                : "🗑 Xóa toàn bộ đã chọn";\n\n            if (bulkHelp) {\n                bulkHelp.textContent = total > 0\n                    ? (\n                        "Đã chọn " + total +\n                        " đợt. Khi bấm xóa: hệ thống tạo 1 backup chung, " +\n                        "kiểm tra lại toàn bộ và chỉ xóa nếu tất cả đều an toàn."\n                    )\n                    : (\n                        "Chưa chọn đợt nào. Hệ thống chỉ xóa khi toàn bộ " +\n                        "đợt được chọn đều vượt qua kiểm tra an toàn."\n                    );\n            }\n        }\n\n        document.addEventListener("change", function (event) {\n            if (\n                event.target &&\n                event.target.matches &&\n                event.target.matches(\n                    \'.b1311-delete-form \' +\n                    \'input[name="confirm_checked"]\'\n                )\n            ) {\n                refreshBulkDelete();\n            }\n        });\n\n        bulkForm.addEventListener("submit", function (event) {\n            const ids = selectedIds();\n\n            if (!ids.length) {\n                event.preventDefault();\n                alert("Hãy chọn ít nhất một đợt để xóa.");\n                return;\n            }\n\n            const phraseInput =\n                document.getElementById(\n                    "b1311-bulk-confirm-phrase"\n                );\n\n            if (\n                !phraseInput ||\n                String(phraseInput.value || "").trim()\n                    !== "XOA TOAN BO DA CHON"\n            ) {\n                event.preventDefault();\n                alert(\n                    \'Phải nhập chính xác: "XOA TOAN BO DA CHON".\'\n                );\n                return;\n            }\n\n            idContainer.innerHTML = "";\n\n            ids.forEach(function (id) {\n                const hidden = document.createElement("input");\n                hidden.type = "hidden";\n                hidden.name = "batch_ids";\n                hidden.value = String(id);\n                idContainer.appendChild(hidden);\n            });\n\n            const ok = window.confirm(\n                "Xóa " + ids.length + " đợt trống đã chọn?\\\\n\\\\n" +\n                "Hệ thống sẽ tạo MỘT backup database đầy đủ trước khi xóa.\\\\n" +\n                "Nếu chỉ một đợt không còn đủ điều kiện, toàn bộ thao tác sẽ dừng."\n            );\n\n            if (!ok) {\n                event.preventDefault();\n            }\n        });\n\n        refreshBulkDelete();\n    })();\n    </script>\n    {# === BAI_13B_11_3_BULK_SCRIPT_END === #}\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> None:
    target = BACKUP / path.relative_to(PROJECT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)


def restore_file(path: Path) -> None:
    source = BACKUP / path.relative_to(PROJECT)
    if source.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch_router(text: str) -> str:
    required = [
        "BAI_13B_11_PROVINCE_BATCH_ADMIN_START",
        "def _snapshot(",
        "def _references(",
        "def _safety_reason(",
        "def _backup_before_delete(",
        "def _log_delete(",
        "def delete_empty_batch(",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "Router Bài 13B-11 thiếu nền bắt buộc: "
                + marker
            )

    if ROUTER_MARK in text:
        return text

    end_marker = (
        "# === BAI_13B_11_PROVINCE_BATCH_ADMIN_END ==="
    )
    if end_marker not in text:
        raise RuntimeError(
            "Không tìm thấy điểm cuối router Bài 13B-11."
        )

    return text.replace(
        end_marker,
        ROUTER_BLOCK.rstrip() + "\n\n" + end_marker,
        1,
    )


def patch_template(text: str) -> str:
    required = [
        "BÀI 13B-11",
        "3. Xóa đợt tạo nhầm",
        "b1311-delete-form",
        'name="confirm_checked"',
        "Xóa đợt trống",
    ]
    for marker in required:
        if marker not in text:
            raise RuntimeError(
                "Template Bài 13B-11 thiếu nền bắt buộc: "
                + marker
            )

    # Bổ sung batch id cho checkbox nếu chưa có.
    if 'data-batch-id="{{ row.batch.id }}"' not in text:
        needle = 'name="confirm_checked"'
        replacement = (
            'name="confirm_checked"\n'
            '                                            '
            'data-batch-id="{{ row.batch.id }}"'
        )
        text = text.replace(
            needle,
            replacement,
            1,
        )

    if PANEL_MARK not in text:
        select_all_end = (
            "{# === "
            "BAI_13B_11_1_SELECT_ALL_TOOLBAR_END === #}"
        )
        if select_all_end in text:
            text = text.replace(
                select_all_end,
                select_all_end
                + "\n"
                + BULK_PANEL.rstrip(),
                1,
            )
        else:
            heading = (
                "<h2>3. Xóa đợt tạo nhầm — "
                "kiểm soát nghiêm ngặt</h2>"
            )
            if heading not in text:
                raise RuntimeError(
                    "Không tìm thấy điểm chèn bảng xóa hàng loạt."
                )
            text = text.replace(
                heading,
                heading + "\n" + BULK_PANEL.rstrip(),
                1,
            )

    if SCRIPT_MARK not in text:
        if "</body>" not in text:
            raise RuntimeError(
                "Không tìm thấy </body> để chèn JavaScript."
            )
        text = text.replace(
            "</body>",
            BULK_SCRIPT.rstrip() + "\n</body>",
            1,
        )

    return text


def verify() -> None:
    router_text = read_text(ROUTER)
    template_text = read_text(TEMPLATE)

    router_required = [
        ROUTER_MARK,
        '@router.post("/xoa-hang-loat")',
        "BULK_DELETE_CONFIRM_TEXT",
        "XOA TOAN BO DA CHON",
        "BEGIN IMMEDIATE",
        "_backup_before_delete(",
        "_safety_reason(",
        "write_con.rollback()",
        "DELETE FROM survey_batches WHERE id=?",
    ]
    for marker in router_required:
        if marker not in router_text:
            raise RuntimeError(
                "Kiểm tra router sau cài không đạt: "
                + marker
            )

    template_required = [
        PANEL_MARK,
        SCRIPT_MARK,
        "b1311-bulk-delete-form",
        "b1311-bulk-delete-button",
        "/dieu-tra/quan-ly-dot-toan-tinh/xoa-hang-loat",
        "XOA TOAN BO DA CHON",
        'data-batch-id="{{ row.batch.id }}"',
        "Xóa toàn bộ đã chọn",
    ]
    for marker in template_required:
        if marker not in template_text:
            raise RuntimeError(
                "Kiểm tra template sau cài không đạt: "
                + marker
            )

    subprocess.run(
        [sys.executable, "-m", "py_compile", str(ROUTER)],
        cwd=PROJECT,
        check=True,
    )

    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(APP / "templates"))
    )
    env.get_template(
        "surveys/province_batch_admin_v13b11.html"
    )


def main() -> int:
    print("=" * 104)
    print(
        "BÀI 13B-11.3 - XÓA HÀNG LOẠT CÁC ĐỢT TRỐNG ĐÃ CHỌN"
    )
    print("=" * 104)
    print()
    print("BỔ SUNG:")
    print(" - Nút: 🗑 Xóa toàn bộ đã chọn.")
    print(" - Hiển thị số đợt đang chọn ngay trên nút.")
    print(" - Câu xác nhận chung: XOA TOAN BO DA CHON.")
    print()
    print("CƠ CHẾ AN TOÀN:")
    print(" 1. Kiểm tra TẤT CẢ đợt lần 1.")
    print(" 2. Tạo MỘT backup SQLite đầy đủ.")
    print(" 3. integrity_check + foreign_key_check.")
    print(" 4. BEGIN IMMEDIATE.")
    print(" 5. Kiểm tra lại TẤT CẢ đợt lần 2.")
    print(" 6. Chỉ nếu tất cả đạt mới bắt đầu DELETE.")
    print(" 7. Chỉ 1 đợt lỗi -> rollback toàn bộ, không xóa dở.")
    print()
    print("BỘ CÀI:")
    print(" - Chỉ sửa source router + template.")
    print(" - KHÔNG xóa đợt khi cài.")
    print(" - KHÔNG sửa database khi cài.")
    print()

    for path in (ROUTER, TEMPLATE):
        if not path.exists():
            raise RuntimeError(
                f"Không tìm thấy nền Bài 13B-11: {path}"
            )

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(ROUTER)
    backup_file(TEMPLATE)
    print("Backup source:", BACKUP)

    try:
        write_text(
            ROUTER,
            patch_router(read_text(ROUTER)),
        )
        write_text(
            TEMPLATE,
            patch_template(read_text(TEMPLATE)),
        )

        verify()
        clear_cache()

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Router py_compile: OK")
        print(" - Jinja template: OK")
        print(" - Nút xóa toàn bộ đã chọn: OK")
        print(" - Backend kiểm tra 2 lần: OK")
        print(" - Một backup chung trước DELETE: OK")
        print(" - Transaction all-or-nothing: OK")
        print(" - Database trong lúc cài: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.3 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        restore_file(ROUTER)
        restore_file(TEMPLATE)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi bởi bộ cài.")
        print("Backup source:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
