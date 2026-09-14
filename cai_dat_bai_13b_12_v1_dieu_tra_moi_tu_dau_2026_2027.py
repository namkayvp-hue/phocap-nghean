# -*- coding: utf-8 -*-
from __future__ import annotations

import py_compile
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from jinja2 import Environment

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
ACCESS = APP / "access_control.py"
SURVEYS = APP / "routers" / "surveys.py"
NEW_TEMPLATE = APP / "templates" / "surveys" / "new_household_2026_v1.html"

MARK = "BAI_13B_12_V1"
MARK_MENU_HIDE = MARK + "_HIDE_HOUSEHOLD_UPDATE_XA"
MARK_MENU_NEW = MARK + "_NEW_HOUSEHOLD_MENU"
MARK_ACCESS = MARK + "_BLOCK_HOUSEHOLD_UPDATE_XA"
MARK_ROUTE = MARK + "_NEW_HOUSEHOLD_ROUTE"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_truoc_bai_13b_12_v1_{STAMP}"

NEW_TEMPLATE_TEXT = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Nhập hồ sơ hộ dân mới</title>\n<style>\n*{box-sizing:border-box}\nbody{margin:0;font-family:"Segoe UI",Arial,sans-serif;background:#f4f7fb;color:#23384d}\n.header{background:linear-gradient(135deg,#0b5ca8,#1577d4);color:#fff;padding:22px 20px}\n.header-inner{width:min(1100px,100%);margin:auto;display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap}\n.header h1{margin:0 0 6px;font-size:28px}.header p{margin:0;line-height:1.5}\n.back{display:inline-flex;align-items:center;min-height:42px;padding:0 14px;border-radius:9px;background:rgba(255,255,255,.14);color:#fff;text-decoration:none;font-weight:700;border:1px solid rgba(255,255,255,.3)}\n.container{width:min(1100px,calc(100% - 28px));margin:22px auto 40px}\n.notice{padding:14px 16px;border:1px solid #9fc6eb;border-radius:12px;background:#edf7ff;color:#244e72;line-height:1.55;margin-bottom:18px}\n.panel{background:#fff;border:1px solid #dce5ee;border-radius:16px;padding:20px;box-shadow:0 8px 28px rgba(34,60,84,.07)}\n.panel-head{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:18px}\n.label{margin:0 0 4px;color:#0b6dc6;font-size:12px;font-weight:900;letter-spacing:.08em}.panel h2{margin:0;font-size:22px}\n.context{min-width:260px;padding:10px 12px;border-radius:10px;background:#f5f9fd;border:1px solid #d9e6f1;font-size:13px;line-height:1.5}\n.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field{display:flex;flex-direction:column;gap:7px}.wide{grid-column:1/-1}\n.field label{font-size:14px;font-weight:800;color:#31506d}.req{color:#c62828}\ninput,textarea{width:100%;border:1px solid #cbd8e4;border-radius:10px;padding:11px 12px;font:inherit;color:#1f3348;outline:none;background:#fff}\ninput:focus,textarea:focus{border-color:#0b6dc6;box-shadow:0 0 0 3px rgba(11,109,198,.1)}input[readonly]{background:#f3f6f9;color:#54697b}\n.help{color:#768797;font-size:12px;line-height:1.45}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:20px;padding-top:18px;border-top:1px solid #e5ecf2}\n.button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 16px;border-radius:10px;border:0;font-weight:800;font-size:14px;cursor:pointer;text-decoration:none}\n.primary{background:#0b6dc6;color:#fff}.secondary{background:#eef3f7;color:#31506d}.disabled{background:#e8edf2;color:#8a98a5;cursor:not-allowed}\n.next{margin-top:18px;padding:14px 16px;border-radius:12px;background:#fff8e7;border:1px solid #ecd38b;color:#705618;line-height:1.55}\n@media(max-width:720px){.grid{grid-template-columns:1fr}.wide{grid-column:auto}.header h1{font-size:23px}}\n</style>\n</head>\n<body>\n<header class="header"><div class="header-inner">\n<div><h1>Nhập hồ sơ hộ dân mới</h1><p>Điều tra mới từ đầu năm học <strong>{{ batch.school_year.code }}</strong> · {{ batch.commune.name }}</p></div>\n<a class="back" href="/dieu-tra/{{ batch.id }}/ho-dan">← Danh sách hộ dân</a>\n</div></header>\n<main class="container">\n<div class="notice"><strong>Nguyên tắc năm học {{ batch.school_year.code }}:</strong> đây là hồ sơ điều tra thực tế mới. Hệ thống không tự lấy địa chỉ, trường, lớp hay tình trạng học tập từ dữ liệu học sinh 2025-2026. Dữ liệu 2025-2026 chỉ được dùng ở bước liên năm/đối chiếu sau này.</div>\n<section class="panel">\n<div class="panel-head"><div><p class="label">HỒ SƠ HỘ DÂN MỚI</p><h2>Thông tin hộ hiện tại</h2></div>\n<div class="context"><div><strong>Xã/phường:</strong> {{ batch.commune.name }}</div><div><strong>Năm học:</strong> {{ batch.school_year.code }}</div><div><strong>Đợt điều tra:</strong> {{ batch.name }}</div></div></div>\n<form method="post" action="/dieu-tra/{{ batch.id }}/ho-dan/them" autocomplete="off">\n<div class="grid">\n<div class="field"><label>Xã/phường hiện tại</label><input type="text" value="{{ batch.commune.name }}" readonly><div class="help">Khóa theo đúng đợt điều tra và phạm vi tài khoản.</div></div>\n<div class="field"><label for="head_name">Họ và tên chủ hộ <span class="req">*</span></label><input id="head_name" name="head_name" type="text" maxlength="200" required autofocus></div>\n<div class="field"><label for="hamlet_name">Thôn/xóm/khối/bản hiện tại</label><input id="hamlet_name" name="hamlet_name" type="text" maxlength="200" placeholder="Nhập theo địa bàn hiện tại sau sáp nhập"></div>\n<div class="field"><label for="phone">Điện thoại liên hệ</label><input id="phone" name="phone" type="text" maxlength="30" inputmode="tel"></div>\n<div class="field wide"><label for="address">Địa chỉ hộ hiện tại <span class="req">*</span></label><textarea id="address" name="address" rows="3" required placeholder="Nhập địa chỉ thực tế hiện nay; không dùng địa chỉ cũ nếu đã thay đổi sau sáp nhập"></textarea></div>\n<div class="field wide"><label for="notes">Ghi chú</label><textarea id="notes" name="notes" rows="3" placeholder="Thông tin cần lưu ý khi điều tra hộ"></textarea></div>\n</div>\n<div class="actions">\n{% if batch.status != \'DA_KET_THUC\' and not batch.is_locked %}\n<button class="button primary" type="submit">Lưu hộ và tạo phiếu điều tra</button>\n{% else %}\n<span class="button disabled">Đợt điều tra đang khóa/kết thúc</span>\n{% endif %}\n<a class="button secondary" href="/dieu-tra/{{ batch.id }}/ho-dan">Hủy / Quay lại</a>\n</div>\n</form>\n<div class="next"><strong>Sau khi tạo phiếu:</strong> hộ mới xuất hiện trong “Danh sách hộ dân / phiếu được giao” với trạng thái <strong>Chưa điều tra</strong>. Tiếp theo mở <strong>Nhập nhanh</strong> để nhập các thành viên thực tế và chọn trường/lớp theo danh mục <strong>{{ batch.school_year.code }}</strong> hiện hành.</div>\n</section>\n</main>\n</body>\n</html>\n'
NEW_ROUTE = '\n# === BAI_13B_12_V1_NEW_HOUSEHOLD_ROUTE_START ===\n@router.get(\n    "/{batch_id}/ho-dan/nhap-ho-so-moi",\n    response_class=HTMLResponse,\n)\ndef trang_nhap_ho_so_ho_dan_moi(\n    batch_id: int,\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    batch = lay_dot_dieu_tra(db=db, batch_id=batch_id)\n\n    if batch is None:\n        return RedirectResponse(url="/dieu-tra", status_code=303)\n\n    user = lay_thong_tin_nguoi_dung(request)\n    role_code = normalize_role_code(user.get("role_code"))\n\n    if role_code not in ADMIN_ROLE_CODES and role_code != COMMUNE_ROLE_CODE:\n        return RedirectResponse(\n            url=f"/dieu-tra/{batch.id}/ho-dan",\n            status_code=303,\n        )\n\n    if (\n        role_code == COMMUNE_ROLE_CODE\n        and user.get("commune_id") is not None\n        and int(user.get("commune_id")) != int(batch.commune_id)\n    ):\n        return RedirectResponse(url="/dieu-tra", status_code=303)\n\n    return templates.TemplateResponse(\n        request=request,\n        name="surveys/new_household_2026_v1.html",\n        context={\n            "nguoi_dung": user,\n            "batch": batch,\n        },\n    )\n# === BAI_13B_12_V1_NEW_HOUSEHOLD_ROUTE_END ===\n'


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    rel = path.relative_to(PROJECT)
    dst = BACKUP / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    rel = path.relative_to(PROJECT)
    src = BACKUP / rel
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)
    elif path == NEW_TEMPLATE and path.exists():
        path.unlink()


def db_check() -> tuple[str, int]:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
        return integrity, fk_count
    finally:
        con.close()


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def patch_menu(text: str) -> str:
    if MARK_MENU_HIDE not in text:
        block_marker = "{# === BAI_13B_9_V1A_MENU === #}"
        pos = text.find(block_marker)
        if pos < 0:
            raise RuntimeError("Menu thiếu marker BAI_13B_9_V1A_MENU.")

        window_end = min(len(text), pos + 900)
        window = text[pos:window_end]
        old_condition = "{% if nguoi_dung and nguoi_dung.role_code != 'GIAO_VIEN' %}"
        if old_condition not in window:
            raise RuntimeError("Không tìm thấy điều kiện hiển thị Cập nhật dữ liệu hộ dân.")

        new_condition = (
            "{# === " + MARK_MENU_HIDE + "_START === #}\n"
            "{% if nguoi_dung and nguoi_dung.role_code not in ['GIAO_VIEN', 'XA'] %}"
        )
        window = window.replace(old_condition, new_condition, 1)

        link_pos = window.find('href="/dieu-tra/cap-nhat-ho-dan"')
        endif_pos = window.find("{% endif %}", link_pos)
        if link_pos < 0 or endif_pos < 0:
            raise RuntimeError("Không xác định được đúng block Cập nhật dữ liệu hộ dân.")

        window = (
            window[:endif_pos]
            + "{# === " + MARK_MENU_HIDE + "_END === #}\n"
            + window[endif_pos:]
        )
        text = text[:pos] + window + text[window_end:]

    if MARK_MENU_NEW not in text:
        anchor = "{# === BAI_13B_10_V1_2_MENU_END === #}"
        pos = text.find(anchor)
        if pos < 0:
            raise RuntimeError("Không tìm thấy điểm chèn sau 2.2.7 cấp Xã.")
        insert_pos = pos + len(anchor)
        block = """
                                {# === BAI_13B_12_V1_NEW_HOUSEHOLD_MENU_START === #}
                                {% if menu_role == 'XA' %}
                                <a
                                    href="/dieu-tra"
                                    data-batch-template="/dieu-tra/{batch_id}/ho-dan/nhap-ho-so-moi"
                                    role="menuitem"
                                >
                                    2.2.8. Nhập hồ sơ hộ dân mới
                                </a>
                                {% endif %}
                                {# === BAI_13B_12_V1_NEW_HOUSEHOLD_MENU_END === #}
"""
        text = text[:insert_pos] + block + text[insert_pos:]

    return text


def patch_access(text: str) -> str:
    if MARK_ACCESS in text:
        return text

    start_marker = "if is_household_update_center or is_household_update_batch:"
    pos = text.find(start_marker)
    if pos < 0:
        raise RuntimeError("Không tìm thấy block phân quyền cap-nhat-ho-dan.")

    window_end = min(len(text), pos + 1100)
    window = text[pos:window_end]
    allowed_pos = window.find("allowed_roles = {")
    close_pos = window.find("}", allowed_pos)
    if allowed_pos < 0 or close_pos < 0:
        raise RuntimeError("Không tìm thấy allowed_roles của cap-nhat-ho-dan.")

    allowed_block = window[allowed_pos:close_pos + 1]
    if "COMMUNE_ROLE_CODE" not in allowed_block:
        raise RuntimeError("allowed_roles hiện không còn COMMUNE_ROLE_CODE; dừng an toàn.")

    new_allowed = re.sub(
        r"^[ \t]*COMMUNE_ROLE_CODE,[ \t]*\r?\n",
        "",
        allowed_block,
        count=1,
        flags=re.M,
    )
    if new_allowed == allowed_block:
        raise RuntimeError("Không loại được quyền XA khỏi cap-nhat-ho-dan.")

    marker_text = (
        "# === " + MARK_ACCESS + "_START ===\n"
        + new_allowed
        + "\n# === " + MARK_ACCESS + "_END ==="
    )
    window = window[:allowed_pos] + marker_text + window[close_pos + 1:]
    return text[:pos] + window + text[window_end:]


def patch_surveys(text: str) -> str:
    if MARK_ROUTE in text:
        return text

    anchor = '@router.post("/{batch_id}/ho-dan/them")'
    pos = text.find(anchor)
    if pos < 0:
        raise RuntimeError("Không tìm thấy route them_ho_dan hiện có.")

    nearby = text[max(0, pos - 1800):min(len(text), pos + 9000)]
    for marker in ("def them_ho_dan(", "tao_ma_ho(", "tao_so_phieu(", 'status="CHUA_DIEU_TRA"'):
        if marker not in nearby:
            raise RuntimeError("Route thêm hộ hiện tại thiếu marker: " + marker)

    return text[:pos] + NEW_ROUTE.strip() + "\n\n\n" + text[pos:]


def verify_source() -> None:
    menu_text = read_text(MENU)
    access_text = read_text(ACCESS)
    surveys_text = read_text(SURVEYS)
    template_text = read_text(NEW_TEMPLATE)

    for marker in (
        MARK_MENU_HIDE + "_START",
        MARK_MENU_HIDE + "_END",
        MARK_MENU_NEW + "_START",
        MARK_MENU_NEW + "_END",
        "2.2.1. Danh sách hộ dân / phiếu được giao",
        "2.2.4. Nhập Excel cập nhật hộ dân",
        "2.2.5. Trường tham gia và khóa/mở trường",
        "2.2.7. GV trường gửi về xã/phường",
        "2.2.8. Nhập hồ sơ hộ dân mới",
        "/ho-dan/nhap-ho-so-moi",
        "/dieu-tra/cap-nhat-ho-dan",
    ):
        if marker not in menu_text:
            raise RuntimeError("Kiểm tra menu thiếu: " + marker)

    block_pos = menu_text.find("BAI_13B_9_V1A_MENU")
    update_block = menu_text[block_pos:min(len(menu_text), block_pos + 1000)]
    if "role_code not in ['GIAO_VIEN', 'XA']" not in update_block:
        raise RuntimeError("Menu Cập nhật dữ liệu hộ dân chưa ẩn đúng với XA.")

    if MARK_ACCESS not in access_text:
        raise RuntimeError("Thiếu marker chặn route cap-nhat-ho-dan cho XA.")

    access_pos = access_text.find(MARK_ACCESS + "_START")
    access_end = access_text.find(MARK_ACCESS + "_END", access_pos)
    if "COMMUNE_ROLE_CODE" in access_text[access_pos:access_end]:
        raise RuntimeError("Access block vẫn còn quyền XA.")

    for marker in (
        MARK_ROUTE + "_START",
        "/{batch_id}/ho-dan/nhap-ho-so-moi",
        "surveys/new_household_2026_v1.html",
        '@router.post("/{batch_id}/ho-dan/them")',
        "tao_ma_ho(",
        "tao_so_phieu(",
    ):
        if marker not in surveys_text:
            raise RuntimeError("Kiểm tra surveys.py thiếu: " + marker)

    for marker in (
        "Nhập hồ sơ hộ dân mới",
        "Lưu hộ và tạo phiếu điều tra",
        "Dữ liệu 2025-2026 chỉ được dùng",
        'action="/dieu-tra/{{ batch.id }}/ho-dan/them"',
    ):
        if marker not in template_text:
            raise RuntimeError("Template mới thiếu: " + marker)

    py_compile.compile(str(SURVEYS), doraise=True)
    py_compile.compile(str(ACCESS), doraise=True)
    env = Environment()
    env.parse(menu_text)
    env.parse(template_text)


def main() -> int:
    global PROJECT, APP, DB, MENU, ACCESS, SURVEYS, NEW_TEMPLATE, BACKUP

    if not APP.is_dir():
        PROJECT = Path.cwd().resolve()
        APP = PROJECT / "app"
        DB = PROJECT / "data" / "phocap.db"
        MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
        ACCESS = APP / "access_control.py"
        SURVEYS = APP / "routers" / "surveys.py"
        NEW_TEMPLATE = APP / "templates" / "surveys" / "new_household_2026_v1.html"
        BACKUP = PROJECT / "exports" / f"backup_truoc_bai_13b_12_v1_{STAMP}"

    print("=" * 112)
    print("BÀI 13B-12 V1 - ĐIỀU TRA MỚI TỪ ĐẦU NĂM HỌC 2026-2027")
    print("=" * 112)
    print("Dự án:", PROJECT)
    print()

    for path in (MENU, ACCESS, SURVEYS, DB):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu file:", path)
            return 2

    menu_before = read_text(MENU)
    access_before = read_text(ACCESS)
    surveys_before = read_text(SURVEYS)

    if (
        MARK_MENU_NEW in menu_before
        and MARK_ACCESS in access_before
        and MARK_ROUTE in surveys_before
        and NEW_TEMPLATE.is_file()
    ):
        print("Bài 13B-12 V1 đã có đầy đủ. Không cài lặp.")
        return 0

    if "BAI_13B_9_V1A_MENU" not in menu_before:
        print("DỪNG AN TOÀN: menu khác bản khảo sát (thiếu BAI_13B_9_V1A_MENU).")
        return 3

    if "BAI_13B_10_V1_2_MENU_END" not in menu_before:
        print("DỪNG AN TOÀN: menu khác bản khảo sát (thiếu BAI_13B_10_V1_2_MENU_END).")
        return 4

    if '@router.post("/{batch_id}/ho-dan/them")' not in surveys_before:
        print("DỪNG AN TOÀN: surveys.py khác bản khảo sát (thiếu route thêm hộ).")
        return 5

    integrity, fk_count = db_check()
    print("Database integrity_check:", integrity)
    print("Database foreign_key_check:", fk_count, "lỗi")
    if integrity.lower() != "ok" or fk_count != 0:
        print("DỪNG AN TOÀN: database chưa đạt kiểm tra.")
        return 6

    BACKUP.mkdir(parents=True, exist_ok=False)
    for path in (MENU, ACCESS, SURVEYS, DB, NEW_TEMPLATE):
        backup_file(path)
    print("Đã backup:", BACKUP)
    print()

    try:
        write_text(MENU, patch_menu(menu_before))
        write_text(ACCESS, patch_access(access_before))
        write_text(SURVEYS, patch_surveys(surveys_before))
        write_text(NEW_TEMPLATE, NEW_TEMPLATE_TEXT)
        verify_source()
        clear_cache()
    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC SOURCE...")
        print(f"{type(exc).__name__}: {exc}")
        for path in (MENU, ACCESS, SURVEYS, NEW_TEMPLATE):
            restore_file(path)
        clear_cache()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi bởi bộ cài.")
        print("Backup:", BACKUP)
        return 7

    integrity_after, fk_after = db_check()
    report = PROJECT / "exports" / f"bao_cao_cai_bai_13b_12_v1_{STAMP}.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        "\n".join([
            "BÁO CÁO CÀI BÀI 13B-12 V1",
            f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"Dự án: {PROJECT}",
            "",
            "ĐÃ CÀI:",
            "1. Cấp Xã không còn thấy 'Cập nhật dữ liệu hộ dân'.",
            "2. Cấp Xã bị chặn truy cập trực tiếp route /dieu-tra/cap-nhat-ho-dan.",
            "3. Thêm menu 2.2.8. Nhập hồ sơ hộ dân mới.",
            "4. Màn hình hồ sơ mới dùng dữ liệu địa chỉ hiện tại của năm 2026-2027.",
            "5. Tái sử dụng backend them_ho_dan hiện có để tự sinh mã hộ + số phiếu + trạng thái CHUA_DIEU_TRA.",
            "6. Không kế thừa địa chỉ/trường/lớp từ dữ liệu học sinh 2025-2026.",
            "7. Không xóa hoặc đổi tên các mục 2.2.x đã hoạt động.",
            "8. Không thay đổi cấu trúc database.",
            "",
            f"Backup: {BACKUP}",
            f"integrity_check sau cài: {integrity_after}",
            f"foreign_key_check sau cài: {fk_after} lỗi",
        ]) + "\n",
        encoding="utf-8-sig",
    )

    print("=" * 112)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V1")
    print("=" * 112)
    print(" - Ẩn + chặn Cập nhật dữ liệu hộ dân đối với cấp Xã.")
    print(" - Thêm 2.2.8. Nhập hồ sơ hộ dân mới.")
    print(" - Dùng lại cơ chế tự sinh mã hộ / số phiếu hiện có.")
    print(" - Giữ nguyên các mục 2.2 hiện có.")
    print(" - Không thay đổi cấu trúc database.")
    print("Backup:", BACKUP)
    print("Báo cáo:", report)
    print()
    print("KIỂM TRA: Xã -> năm 2026-2027 -> 2 -> 2.2 -> 2.2.8 -> tạo 1 hộ thử.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
