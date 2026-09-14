from __future__ import annotations

import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
APP = PROJECT / "app"

ROUTER = APP / "routers" / "household_updates.py"
CENTER = APP / "templates" / "surveys" / "household_update_center_v1.html"
DETAIL = APP / "templates" / "surveys" / "household_import_detail_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_bai_13b_9_v1b_1_xoa_file_loi_{STAMP}"

MARK_STATUS = "BAI_13B_9_V1B_1_DELETABLE_STATUSES"
MARK_ROUTE = "BAI_13B_9_V1B_1_DELETE_ROUTE"
MARK_CENTER = "BAI_13B_9_V1B_1_DELETE_CENTER"
MARK_DETAIL = "BAI_13B_9_V1B_1_DELETE_DETAIL"

DELETEABLE_BLOCK = '\n# === BAI_13B_9_V1B_1_DELETABLE_STATUSES_START ===\nDELETEABLE_IMPORT_STATUSES = frozenset(\n    {\n        "DA_KIEM_TRA_CAU_TRUC",\n        "LOI_DU_LIEU",\n        "LOI_CAP_NHAT",\n        "CHO_XU_LY_XLS",\n        "TRUNG_FILE",\n        "LOI_DINH_DANG",\n        "LOI_FILE",\n        "LOI_DOT_KHOA",\n        "CO_XUNG_DOT",\n    }\n)\n# === BAI_13B_9_V1B_1_DELETABLE_STATUSES_END ===\n'
DELETE_ROUTE = '\n# === BAI_13B_9_V1B_1_DELETE_ROUTE_START ===\n@router.post("/cap-nhat-ho-dan/lan-gui/{job_code}/xoa")\ndef delete_household_import_job(\n    job_code: str,\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) not in UPLOAD_ROLE_CODES:\n        return RedirectResponse(\n            url="/?status=forbidden",\n            status_code=303,\n        )\n\n    job = _job_in_scope(\n        db,\n        request,\n        job_code,\n    )\n    if job is None:\n        return RedirectResponse(\n            url="/dieu-tra/cap-nhat-ho-dan",\n            status_code=303,\n        )\n\n    if job.status not in DELETEABLE_IMPORT_STATUSES:\n        return RedirectResponse(\n            url=(\n                f"/dieu-tra/cap-nhat-ho-dan/lan-gui/{job.job_code}"\n                "?delete_error=not_allowed"\n            ),\n            status_code=303,\n        )\n\n    batch_id = int(job.survey_batch_id)\n    stored_path_value = (job.stored_path or "").strip()\n\n    other_file_reference = None\n    if stored_path_value:\n        other_file_reference = db.scalar(\n            select(HouseholdImportJob.id)\n            .where(\n                HouseholdImportJob.id != job.id,\n                HouseholdImportJob.stored_path == stored_path_value,\n            )\n            .limit(1)\n        )\n\n    issue_rows = list(\n        db.scalars(\n            select(HouseholdImportError).where(\n                HouseholdImportError.job_id == job.id\n            )\n        ).all()\n    )\n    for issue in issue_rows:\n        db.delete(issue)\n\n    db.delete(job)\n    db.commit()\n\n    if stored_path_value and other_file_reference is None:\n        try:\n            file_path = (\n                PROJECT_DIR / Path(stored_path_value)\n            ).resolve()\n            import_root = IMPORT_ROOT.resolve()\n\n            if (\n                file_path == import_root\n                or import_root in file_path.parents\n            ):\n                if file_path.is_file():\n                    file_path.unlink()\n        except Exception:\n            pass\n\n    return RedirectResponse(\n        url=(\n            "/dieu-tra/cap-nhat-ho-dan"\n            f"?batch_id={batch_id}&deleted=1"\n        ),\n        status_code=303,\n    )\n# === BAI_13B_9_V1B_1_DELETE_ROUTE_END ===\n'
CENTER_NOTICE = '\n    <!-- === BAI_13B_9_V1B_1_DELETE_CENTER_START === -->\n    {% if request.query_params.get(\'deleted\') == \'1\' %}\n    <section class="panel">\n        <div class="notice" style="border-color:#a5d6a7;background:#f1f8e9;color:#256029">\n            <strong>Đã xóa lần gửi.</strong>\n            Lịch sử lỗi và file lưu tạm của lần gửi đã được dọn.\n            Dữ liệu hộ dân đã cập nhật thành công trước đó không bị ảnh hưởng.\n        </div>\n    </section>\n    {% endif %}\n    <!-- === BAI_13B_9_V1B_1_DELETE_CENTER_END === -->\n'
CENTER_CELL_NEW = '\n<td>\n    <a class="btn secondary" href="/dieu-tra/cap-nhat-ho-dan/lan-gui/{{ job.job_code }}">Xem kết quả</a>\n    {% if job.status == \'DA_CAP_NHAT\' %}\n    <a class="btn primary" style="margin-top:6px" href="/dieu-tra/{{ job.survey_batch_id }}/ho-dan">Xem dữ liệu đã cập nhật</a>\n    {% elif can_upload and job.status in [\'DA_KIEM_TRA_CAU_TRUC\',\'LOI_DU_LIEU\',\'LOI_CAP_NHAT\',\'CHO_XU_LY_XLS\',\'TRUNG_FILE\',\'LOI_DINH_DANG\',\'LOI_FILE\',\'LOI_DOT_KHOA\',\'CO_XUNG_DOT\'] %}\n    <form\n        method="post"\n        action="/dieu-tra/cap-nhat-ho-dan/lan-gui/{{ job.job_code }}/xoa"\n        style="margin-top:6px"\n        onsubmit="return confirm(\'Xóa lần gửi {{ job.job_code }}? File lỗi và lịch sử lỗi của lần gửi này sẽ bị xóa. Dữ liệu hộ dân đã cập nhật thành công sẽ không bị xóa.\');"\n    >\n        <button\n            class="btn"\n            type="submit"\n            style="background:#c62828;color:#fff;border-color:#c62828"\n        >🗑 Xóa</button>\n    </form>\n    {% endif %}\n</td>\n'
DETAIL_DELETE_UI = '\n        <!-- === BAI_13B_9_V1B_1_DELETE_DETAIL_START === -->\n        {% if can_delete %}\n        <form\n            method="post"\n            action="/dieu-tra/cap-nhat-ho-dan/lan-gui/{{ job.job_code }}/xoa"\n            style="margin-top:14px"\n            onsubmit="return confirm(\'Bạn chắc chắn muốn xóa lần gửi {{ job.job_code }}? Lịch sử lỗi và file lưu tạm sẽ bị xóa. Thao tác này không xóa dữ liệu hộ dân đã cập nhật thành công.\');"\n        >\n            <button\n                class="btn"\n                type="submit"\n                style="background:#c62828;color:#fff;border-color:#c62828"\n            >🗑 Xóa lần gửi / file lỗi</button>\n        </form>\n        {% endif %}\n        <!-- === BAI_13B_9_V1B_1_DELETE_DETAIL_END === -->\n'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp bắt buộc: {path}")
    return path.read_text(encoding="utf-8-sig")


def backup_file(path: Path) -> None:
    rel = path.relative_to(PROJECT)
    dst = BACKUP / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch_router(text_value: str) -> str:
    required = [
        'IMPORT_STATUS_LABELS = {',
        'IMPORT_STATUS_CLASSES = {',
        'def _job_in_scope(',
        '@router.post("/cap-nhat-ho-dan/lan-gui/{job_code}/xu-ly")',
        '"DA_CAP_NHAT"',
        'IMPORT_ROOT =',
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(
                f"household_updates.py thiếu nền V1B: {marker}"
            )

    if MARK_STATUS not in text_value:
        anchor = "\n\ndef _user(request: Request) -> dict:\n"
        if anchor not in text_value:
            raise RuntimeError(
                "Không tìm thấy điểm chèn danh sách trạng thái có thể xóa."
            )
        text_value = text_value.replace(
            anchor,
            "\n\n" + DELETEABLE_BLOCK.strip() + anchor,
            1,
        )

    if MARK_ROUTE not in text_value:
        anchor = '@router.post("/cap-nhat-ho-dan/lan-gui/{job_code}/xu-ly")'
        pos = text_value.find(anchor)
        if pos < 0:
            raise RuntimeError(
                "Không tìm thấy route xử lý lại file V1B."
            )
        text_value = (
            text_value[:pos]
            + DELETE_ROUTE.strip()
            + "\n\n\n"
            + text_value[pos:]
        )

    if '"can_delete": (' not in text_value:
        anchor = """            "status_class": IMPORT_STATUS_CLASSES.get(
                job.status,
                "info",
            ),
"""
        if anchor not in text_value:
            raise RuntimeError(
                "Không tìm thấy context trang chi tiết lần gửi."
            )

        replacement = anchor + """            "can_delete": (
                _role(request) in UPLOAD_ROLE_CODES
                and job.status in DELETEABLE_IMPORT_STATUSES
            ),
"""
        text_value = text_value.replace(
            anchor,
            replacement,
            1,
        )

    return text_value


def patch_center(text_value: str) -> str:
    if MARK_CENTER in text_value:
        return text_value

    required = [
        "Lịch sử gửi Excel",
        "Xem kết quả",
        "job.status == 'DA_CAP_NHAT'",
        "can_upload",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(
                f"household_update_center_v1.html thiếu nền V1B: {marker}"
            )

    main_anchor = '<main class="wrap">'
    if main_anchor not in text_value:
        raise RuntimeError('Không tìm thấy <main class="wrap">.')

    text_value = text_value.replace(
        main_anchor,
        main_anchor + "\n" + CENTER_NOTICE,
        1,
    )

    cell_old = """<td><a class="btn secondary" href="/dieu-tra/cap-nhat-ho-dan/lan-gui/{{ job.job_code }}">Xem kết quả</a>
                            {% if job.status == 'DA_CAP_NHAT' %}<a class="btn primary" style="margin-top:6px" href="/dieu-tra/{{ job.survey_batch_id }}/ho-dan">Xem dữ liệu đã cập nhật</a>{% endif %}</td>"""

    if cell_old not in text_value:
        raise RuntimeError(
            "Không tìm thấy ô Chi tiết V1B để thêm nút Xóa."
        )

    return text_value.replace(
        cell_old,
        CENTER_CELL_NEW.strip(),
        1,
    )


def patch_detail(text_value: str) -> str:
    if MARK_DETAIL in text_value:
        return text_value

    required = [
        "KẾT QUẢ TIẾP NHẬN FILE",
        "Kiểm tra / xử lý lại file đã lưu",
        "job.status == 'DA_CAP_NHAT'",
    ]
    for marker in required:
        if marker not in text_value:
            raise RuntimeError(
                f"household_import_detail_v1.html thiếu nền V1B: {marker}"
            )

    anchor = """        {% if sheet_names %}
        <p><strong>Sheet phát hiện:</strong> {{ sheet_names|join(', ') }}</p>
        {% endif %}
"""

    if anchor not in text_value:
        raise RuntimeError(
            "Không tìm thấy điểm chèn nút Xóa ở trang chi tiết."
        )

    return text_value.replace(
        anchor,
        DETAIL_DELETE_UI + "\n" + anchor,
        1,
    )


def verify() -> None:
    router_text = read_text(ROUTER)
    center_text = read_text(CENTER)
    detail_text = read_text(DETAIL)

    checks = [
        (MARK_STATUS, router_text),
        (MARK_ROUTE, router_text),
        ("DELETEABLE_IMPORT_STATUSES", router_text),
        ('/{job_code}/xoa"', router_text),
        ("db.delete(job)", router_text),
        ("HouseholdImportError.job_id == job.id", router_text),
        (MARK_CENTER, center_text),
        ("🗑 Xóa", center_text),
        (MARK_DETAIL, detail_text),
        ("🗑 Xóa lần gửi / file lỗi", detail_text),
        ("can_delete", detail_text),
    ]
    for marker, text_value in checks:
        if marker not in text_value:
            raise RuntimeError(
                f"Kiểm tra sau cài chưa đạt: {marker}"
            )

    delete_route_start = router_text.find(
        "# === BAI_13B_9_V1B_1_DELETE_ROUTE_START ==="
    )
    delete_route_end = router_text.find(
        "# === BAI_13B_9_V1B_1_DELETE_ROUTE_END ==="
    )
    delete_block = router_text[
        delete_route_start:delete_route_end
    ]

    for marker in [
        "db.delete(household)",
        "db.delete(person)",
        "DELETE FROM households",
        "DELETE FROM survey_people",
        "DELETE FROM survey_forms",
    ]:
        if marker in delete_block:
            raise RuntimeError(
                "Route xóa có dấu hiệu đụng dữ liệu hộ dân: "
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
    env.get_template("surveys/household_update_center_v1.html")
    env.get_template("surveys/household_import_detail_v1.html")


def main() -> int:
    print("=" * 108)
    print("BÀI 13B-9 V1B.1 - THÊM NÚT XÓA FILE/LẦN GỬI LỖI")
    print("=" * 108)
    print("")
    print("SAU KHI CÀI:")
    print(" - File/lần gửi lỗi có nút Xóa.")
    print(" - File trùng, xung đột, XLS chờ xử lý hoặc đã kiểm tra nhưng chưa cập nhật cũng có thể xóa.")
    print(" - Xóa bản ghi lần gửi + chi tiết lỗi + file lưu tạm trên máy chủ nếu có.")
    print(" - KHÔNG cho xóa lần gửi đã 'Đã cập nhật thành công'.")
    print(" - KHÔNG xóa hộ dân, phiếu điều tra hoặc thành viên.")
    print("")
    print("KHÔNG THAY ĐỔI:")
    print(" - Dữ liệu hộ dân đã cập nhật thành công.")
    print(" - Quyền 2.2–2.5 vừa sửa.")
    print(" - Logic xử lý Excel V1B.")
    print("")

    for path in (ROUTER, CENTER, DETAIL):
        if not path.exists():
            raise RuntimeError(f"Không tìm thấy: {path}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    for path in (ROUTER, CENTER, DETAIL):
        backup_file(path)

    try:
        ROUTER.write_text(
            patch_router(read_text(ROUTER)),
            encoding="utf-8",
        )
        CENTER.write_text(
            patch_center(read_text(CENTER)),
            encoding="utf-8",
        )
        DETAIL.write_text(
            patch_detail(read_text(DETAIL)),
            encoding="utf-8",
        )

        verify()
        clear_cache()

        print("")
        print("CAI DAT BAI 13B-9 V1B.1 THANH CONG")
        print("Backup:", BACKUP)
        print("")
        print("Khởi động lại Uvicorn và Ctrl + F5.")
        print("Dòng file lỗi trong Lịch sử gửi Excel phải có nút Xóa.")
        return 0

    except Exception:
        traceback.print_exc()
        print("")
        print("CÓ LỖI - ĐANG KHÔI PHỤC...")
        for path in (ROUTER, CENTER, DETAIL):
            restore_file(path)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE VỀ TRƯỚC V1B.1.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
