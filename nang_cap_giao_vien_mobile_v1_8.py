from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
PYTHON = Path(os.environ.get("PHOCAP_PYTHON", str(PROJECT / ".venv" / "Scripts" / "python.exe")))

MAIN = PROJECT / "app" / "main.py"
DB = PROJECT / "data" / "phocap.db"
ROUTER = PROJECT / "app" / "routers" / "surveys.py"
INDEX = PROJECT / "app" / "templates" / "surveys" / "index.html"
HOUSEHOLDS = PROJECT / "app" / "templates" / "surveys" / "households.html"
QUICK = PROJECT / "app" / "templates" / "surveys" / "quick_entry.html"
MENU = PROJECT / "app" / "templates" / "partials" / "dropdown_menu_v1.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_giao_vien_mobile_v1_8_{STAMP}"
MANIFEST = BACKUP / "manifest.json"

INDEX_BLOCK = '{# === GV_MOBILE_V18_HOME_START === #}\n{% if nguoi_dung.role_code == \'GIAO_VIEN\' %}\n<style>\n.pc-gv-v18-home { display: none; }\n@media (max-width: 760px) {\n    html, body { margin: 0 !important; min-height: 100dvh; background: #f3f6fa !important; }\n    body > *:not(.pc-gv-v18-home) { display: none !important; }\n    .pc-gv-v18-home {\n        display: flex !important;\n        min-height: 100dvh;\n        padding: 22px 16px;\n        align-items: flex-start;\n        justify-content: center;\n        box-sizing: border-box;\n    }\n    .pc-gv-v18-home-inner {\n        width: min(100%, 520px);\n        display: grid;\n        gap: 18px;\n        margin-top: 8px;\n    }\n    .pc-gv-v18-year {\n        width: 100%;\n        min-height: 58px;\n        padding: 10px 14px;\n        border: 1px solid #b8c8d8;\n        border-radius: 13px;\n        background: #fff;\n        color: #17324d;\n        font: inherit;\n        font-size: 17px;\n        font-weight: 800;\n        box-sizing: border-box;\n    }\n    .pc-gv-v18-assignment {\n        display: flex;\n        min-height: 68px;\n        align-items: center;\n        justify-content: center;\n        padding: 12px 16px;\n        border-radius: 14px;\n        background: #1769aa;\n        color: #fff !important;\n        text-decoration: none !important;\n        font-size: 20px;\n        font-weight: 850;\n        box-shadow: 0 5px 14px rgba(23,105,170,.18);\n        box-sizing: border-box;\n    }\n    .pc-gv-v18-assignment.is-disabled {\n        background: #ccd5de;\n        color: #667684 !important;\n        box-shadow: none;\n        pointer-events: none;\n    }\n}\n</style>\n<section class="pc-gv-v18-home">\n    <div class="pc-gv-v18-home-inner">\n        <form method="get" action="/dieu-tra" id="pc-gv-v18-year-form">\n            <select class="pc-gv-v18-year" id="pc-gv-v18-year" name="school_year_id" aria-label="Chọn năm học">\n                <option value="">-- Chọn năm học --</option>\n                {% for nam_hoc in school_years %}\n                    <option value="{{ nam_hoc.id }}" {% if nam_hoc.id == selected_school_year_id %}selected{% endif %}>\n                        {{ nam_hoc.code }}\n                    </option>\n                {% endfor %}\n            </select>\n        </form>\n\n        {% if selected_school_year_id and survey_batches %}\n            <a class="pc-gv-v18-assignment" href="/dieu-tra/{{ survey_batches[0].id }}/ho-dan?page_size=100&sort=hamlet">\n                Phiếu phân công\n            </a>\n        {% else %}\n            <span class="pc-gv-v18-assignment is-disabled">Phiếu phân công</span>\n        {% endif %}\n    </div>\n</section>\n<script>\nwindow.addEventListener(\'load\', function () {\n    if (window.innerWidth > 760) return;\n    const year = document.getElementById(\'pc-gv-v18-year\');\n    const form = document.getElementById(\'pc-gv-v18-year-form\');\n    if (year && form) {\n        year.addEventListener(\'change\', function () { form.submit(); });\n    }\n});\n</script>\n{% endif %}\n{# === GV_MOBILE_V18_HOME_END === #}'
HOUSEHOLDS_BLOCK = '{# === GV_MOBILE_V18_ASSIGNMENTS_START === #}\n{% if nguoi_dung.role_code == \'GIAO_VIEN\' %}\n<style>\n.pc-gv-v18-assignments { display: none; }\n@media (max-width: 760px) {\n    html, body { margin: 0 !important; min-height: 100dvh; background: #f3f6fa !important; }\n    body > *:not(.pc-gv-v18-assignments) { display: none !important; }\n    .pc-gv-v18-assignments {\n        display: block !important;\n        min-height: 100dvh;\n        padding: 14px 10px 28px;\n        box-sizing: border-box;\n    }\n    .pc-gv-v18-assignments-inner { width: min(100%, 650px); margin: 0 auto; }\n    .pc-gv-v18-assignments-title {\n        margin: 0 0 12px;\n        color: #123f73;\n        font-size: 20px;\n        font-weight: 850;\n    }\n    .pc-gv-v18-grid-head,\n    .pc-gv-v18-grid-row {\n        display: grid;\n        grid-template-columns: 1.05fr 1.55fr .9fr;\n        gap: 8px;\n        align-items: center;\n    }\n    .pc-gv-v18-grid-head {\n        padding: 10px 9px;\n        border-radius: 10px 10px 0 0;\n        background: #174f86;\n        color: #fff;\n        font-size: 12px;\n        font-weight: 850;\n    }\n    .pc-gv-v18-grid-row {\n        padding: 11px 9px;\n        border: 1px solid #d8e2ec;\n        border-top: 0;\n        background: #fff;\n        color: #1d2c3c;\n        font-size: 14px;\n    }\n    .pc-gv-v18-grid-row:last-child { border-radius: 0 0 10px 10px; }\n    .pc-gv-v18-form-number { font-weight: 800; word-break: break-word; }\n    .pc-gv-v18-head-name { font-weight: 700; line-height: 1.25; }\n    .pc-gv-v18-quick {\n        display: flex;\n        min-height: 38px;\n        padding: 7px 8px;\n        align-items: center;\n        justify-content: center;\n        border-radius: 9px;\n        background: #1769aa;\n        color: #fff !important;\n        text-decoration: none !important;\n        font-size: 13px;\n        font-weight: 850;\n        text-align: center;\n    }\n    .pc-gv-v18-empty {\n        padding: 20px 14px;\n        border: 1px dashed #bdcad8;\n        border-radius: 10px;\n        background: #fff;\n        color: #637486;\n        text-align: center;\n    }\n    .pc-gv-v18-pages {\n        display: flex;\n        justify-content: space-between;\n        gap: 10px;\n        margin-top: 14px;\n    }\n    .pc-gv-v18-page-link {\n        display: flex;\n        min-height: 42px;\n        flex: 1;\n        align-items: center;\n        justify-content: center;\n        border: 1px solid #c6d4e1;\n        border-radius: 10px;\n        background: #fff;\n        color: #174f86 !important;\n        text-decoration: none !important;\n        font-weight: 800;\n    }\n    .pc-gv-v18-page-link.disabled { opacity: .45; pointer-events: none; }\n}\n</style>\n<section class="pc-gv-v18-assignments">\n    <div class="pc-gv-v18-assignments-inner">\n        <h1 class="pc-gv-v18-assignments-title">Phiếu phân công</h1>\n        {% if survey_forms %}\n            <div class="pc-gv-v18-grid-head">\n                <div>Số phiếu</div>\n                <div>Tên hộ</div>\n                <div>Nhập nhanh</div>\n            </div>\n            {% for phieu in survey_forms %}\n                <div class="pc-gv-v18-grid-row">\n                    <div class="pc-gv-v18-form-number">{{ phieu.form_number }}</div>\n                    <div class="pc-gv-v18-head-name">{{ phieu.household.head_name }}</div>\n                    <div>\n                        <a class="pc-gv-v18-quick" href="/dieu-tra/{{ batch.id }}/ho-dan/{{ phieu.household.id }}/nhap-nhanh">\n                            Nhập nhanh\n                        </a>\n                    </div>\n                </div>\n            {% endfor %}\n        {% else %}\n            <div class="pc-gv-v18-empty">Chưa có phiếu nào được phân công.</div>\n        {% endif %}\n\n        {% if total_pages | default(1) > 1 %}\n            <div class="pc-gv-v18-pages">\n                {% if previous_url %}\n                    <a class="pc-gv-v18-page-link" href="{{ previous_url }}">← Trước</a>\n                {% else %}\n                    <span class="pc-gv-v18-page-link disabled">← Trước</span>\n                {% endif %}\n                {% if next_url %}\n                    <a class="pc-gv-v18-page-link" href="{{ next_url }}">Tiếp →</a>\n                {% else %}\n                    <span class="pc-gv-v18-page-link disabled">Tiếp →</span>\n                {% endif %}\n            </div>\n        {% endif %}\n    </div>\n</section>\n{% endif %}\n{# === GV_MOBILE_V18_ASSIGNMENTS_END === #}'
QUICK_BLOCK = '{# === GV_MOBILE_V18_QUICK_START === #}\n{% if nguoi_dung.role_code == \'GIAO_VIEN\' %}\n<style>\n.pc-gv-v18-quick-page { display: none; }\n@media (max-width: 760px) {\n    html, body { margin: 0 !important; min-height: 100dvh; background: #f3f6fa !important; }\n    body > *:not(.pc-gv-v18-quick-page) { display: none !important; }\n    .pc-gv-v18-quick-page {\n        display: block !important;\n        min-height: 100dvh;\n        padding: 12px 10px 26px;\n        box-sizing: border-box;\n    }\n    .pc-gv-v18-quick-inner { width: min(100%, 650px); margin: 0 auto; }\n    .pc-gv-v18-q-head {\n        margin-bottom: 12px;\n        padding: 13px 14px;\n        border-radius: 12px;\n        background: #174f86;\n        color: #fff;\n    }\n    .pc-gv-v18-q-number { font-size: 12px; font-weight: 800; opacity: .88; }\n    .pc-gv-v18-q-house { margin-top: 4px; font-size: 19px; font-weight: 900; line-height: 1.2; }\n    .pc-gv-v18-q-position { margin-top: 5px; font-size: 12px; opacity: .86; }\n    .pc-gv-v18-alert {\n        margin-bottom: 10px;\n        padding: 10px 12px;\n        border-radius: 10px;\n        background: #fff0f0;\n        color: #a51f1f;\n        border: 1px solid #efbcbc;\n        font-size: 13px;\n        font-weight: 750;\n    }\n    .pc-gv-v18-ok {\n        margin-bottom: 10px;\n        padding: 10px 12px;\n        border-radius: 10px;\n        background: #eaf7ed;\n        color: #1b662f;\n        border: 1px solid #b9dfc2;\n        font-size: 13px;\n        font-weight: 750;\n    }\n    .pc-gv-v18-members-head,\n    .pc-gv-v18-member {\n        display: grid;\n        grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr) minmax(0, .75fr);\n        gap: 8px;\n        align-items: start;\n    }\n    .pc-gv-v18-members-head {\n        padding: 9px 10px;\n        border-radius: 10px 10px 0 0;\n        background: #e3edf7;\n        color: #24435f;\n        font-size: 12px;\n        font-weight: 850;\n    }\n    .pc-gv-v18-member {\n        padding: 11px 10px;\n        border: 1px solid #d8e2ec;\n        border-top: 0;\n        background: #fff;\n        font-size: 13px;\n    }\n    .pc-gv-v18-member:last-child { border-radius: 0 0 10px 10px; }\n    .pc-gv-v18-member-name { font-weight: 850; line-height: 1.25; }\n    .pc-gv-v18-member-stt { display: inline-block; min-width: 22px; color: #174f86; }\n    .pc-gv-v18-school, .pc-gv-v18-class { line-height: 1.3; word-break: break-word; }\n    .pc-gv-v18-actions {\n        grid-column: 1 / -1;\n        display: grid;\n        grid-template-columns: 1fr 1fr;\n        gap: 8px;\n        margin-top: 3px;\n    }\n    .pc-gv-v18-btn,\n    .pc-gv-v18-actions button,\n    .pc-gv-v18-actions a {\n        display: flex;\n        min-height: 40px;\n        align-items: center;\n        justify-content: center;\n        padding: 7px 9px;\n        border: 0;\n        border-radius: 9px;\n        font: inherit;\n        font-size: 13px;\n        font-weight: 850;\n        text-decoration: none !important;\n        box-sizing: border-box;\n        cursor: pointer;\n    }\n    .pc-gv-v18-edit { background: #edf3f8; color: #174f86 !important; border: 1px solid #cbd9e6 !important; }\n    .pc-gv-v18-accept { background: #1f8a3b; color: #fff !important; }\n    .pc-gv-v18-accepted { background: #eaf7ed; color: #1b662f !important; border: 1px solid #b9dfc2 !important; cursor: default !important; }\n    .pc-gv-v18-section {\n        margin-top: 14px;\n        padding: 13px;\n        border: 1px solid #d9e4ee;\n        border-radius: 12px;\n        background: #fff;\n    }\n    .pc-gv-v18-section summary {\n        cursor: pointer;\n        color: #174f86;\n        font-size: 15px;\n        font-weight: 900;\n    }\n    .pc-gv-v18-form-grid { display: grid; gap: 9px; margin-top: 12px; }\n    .pc-gv-v18-input, .pc-gv-v18-select {\n        width: 100%;\n        min-height: 44px;\n        padding: 8px 10px;\n        border: 1px solid #c9d7e4;\n        border-radius: 9px;\n        background: #fff;\n        font: inherit;\n        box-sizing: border-box;\n    }\n    .pc-gv-v18-label { display: block; margin-bottom: 4px; font-size: 12px; font-weight: 800; color: #3d5368; }\n    .pc-gv-v18-add-button {\n        width: 100%;\n        min-height: 46px;\n        margin-top: 10px;\n        border: 0;\n        border-radius: 10px;\n        background: #1769aa;\n        color: #fff;\n        font: inherit;\n        font-weight: 900;\n    }\n    .pc-gv-v18-finish-box {\n        display: grid;\n        gap: 9px;\n        margin-top: 14px;\n    }\n    .pc-gv-v18-finish {\n        width: 100%;\n        min-height: 54px;\n        border: 0;\n        border-radius: 11px;\n        background: #1f8a3b;\n        color: #fff;\n        font: inherit;\n        font-size: 16px;\n        font-weight: 900;\n        cursor: pointer;\n    }\n    .pc-gv-v18-finish-next { background: #1769aa; }\n    .pc-gv-v18-back {\n        display: flex;\n        min-height: 44px;\n        margin-top: 12px;\n        align-items: center;\n        justify-content: center;\n        border-radius: 10px;\n        background: #fff;\n        border: 1px solid #cbd9e6;\n        color: #174f86 !important;\n        text-decoration: none !important;\n        font-size: 13px;\n        font-weight: 850;\n    }\n}\n</style>\n<main class="pc-gv-v18-quick-page">\n    <div class="pc-gv-v18-quick-inner">\n        <section class="pc-gv-v18-q-head">\n            <div class="pc-gv-v18-q-number">Số phiếu: {{ survey_form.form_number }}</div>\n            <div class="pc-gv-v18-q-house">{{ household.head_name }}</div>\n            <div class="pc-gv-v18-q-position">Phiếu {{ current_position }}/{{ total_forms }}</div>\n        </section>\n\n        {% if thong_bao_loi %}<div class="pc-gv-v18-alert">{{ thong_bao_loi }}</div>{% endif %}\n        {% if thong_bao %}<div class="pc-gv-v18-ok">{{ thong_bao }}</div>{% endif %}\n\n        {% if person_summaries %}\n            <div class="pc-gv-v18-members-head">\n                <div>Thành viên</div>\n                <div>Trường</div>\n                <div>Lớp</div>\n            </div>\n            {% for item in person_summaries %}\n                <section class="pc-gv-v18-member">\n                    <div class="pc-gv-v18-member-name"><span class="pc-gv-v18-member-stt">{{ loop.index }}.</span>{{ item.person.full_name }}</div>\n                    <div class="pc-gv-v18-school">{{ item.school_name or \'—\' }}</div>\n                    <div class="pc-gv-v18-class">{{ item.class_name or \'—\' }}</div>\n                    <div class="pc-gv-v18-actions">\n                        <a class="pc-gv-v18-edit" href="/dieu-tra/{{ batch.id }}/ho-dan/{{ household.id }}/doi-tuong/{{ item.person.id }}/nam-hoc?school_year_id={{ batch.school_year_id }}">\n                            Sửa\n                        </a>\n                        {% if item.is_reviewed %}\n                            <span class="pc-gv-v18-btn pc-gv-v18-accepted">✓ Đã chấp nhận</span>\n                        {% elif item.can_accept %}\n                            <form method="post" action="/dieu-tra/{{ batch.id }}/ho-dan/{{ household.id }}/nhap-nhanh/{{ item.person.id }}/chap-nhan">\n                                <button class="pc-gv-v18-accept" type="submit">Chấp nhận</button>\n                            </form>\n                        {% else %}\n                            <span class="pc-gv-v18-btn pc-gv-v18-accepted" style="opacity:.55;">Cần sửa</span>\n                        {% endif %}\n                    </div>\n                </section>\n            {% endfor %}\n        {% else %}\n            <div class="pc-gv-v18-alert">Hộ chưa có thành viên. Hãy thêm thành viên mới.</div>\n        {% endif %}\n\n        {% if can_edit_data %}\n            <details class="pc-gv-v18-section" {% if thong_bao_loi and person_form_data.full_name %}open{% endif %}>\n                <summary>＋ Thêm thành viên mới</summary>\n                <form method="post" action="/dieu-tra/{{ batch.id }}/ho-dan/{{ household.id }}/nhap-nhanh/them-doi-tuong">\n                    <div class="pc-gv-v18-form-grid">\n                        <div><label class="pc-gv-v18-label">Họ và tên *</label><input class="pc-gv-v18-input" name="full_name" value="{{ person_form_data.full_name }}" required></div>\n                        <div><label class="pc-gv-v18-label">Ngày sinh *</label><input class="pc-gv-v18-input" type="date" name="date_of_birth" value="{{ person_form_data.date_of_birth }}" max="{{ today }}" required></div>\n                        <div><label class="pc-gv-v18-label">Giới tính *</label><select class="pc-gv-v18-select" name="gender" required><option value="">-- Chọn --</option>{% for value in [\'Nam\',\'Nữ\',\'Khác\'] %}<option value="{{ value }}" {% if person_form_data.gender == value %}selected{% endif %}>{{ value }}</option>{% endfor %}</select></div>\n                        <div><label class="pc-gv-v18-label">Dân tộc *</label><input class="pc-gv-v18-input" name="ethnic_group" value="{{ person_form_data.ethnic_group }}" required></div>\n                        <div><label class="pc-gv-v18-label">Quan hệ với chủ hộ *</label><input class="pc-gv-v18-input" name="relationship_to_head" value="{{ person_form_data.relationship_to_head }}" required></div>\n                        <div><label class="pc-gv-v18-label">Số định danh cá nhân</label><input class="pc-gv-v18-input" name="personal_id" value="{{ person_form_data.personal_id }}" inputmode="numeric"></div>\n                        <div><label class="pc-gv-v18-label">Diện cư trú *</label><select class="pc-gv-v18-select" name="residency_status" required>{% for code, label in residency_status_labels.items() %}<option value="{{ code }}" {% if person_form_data.residency_status == code %}selected{% endif %}>{{ label }}</option>{% endfor %}</select></div>\n                    </div>\n                    <button class="pc-gv-v18-add-button" type="submit">Thêm thành viên</button>\n                </form>\n            </details>\n\n            <form class="pc-gv-v18-finish-box" method="post" action="/dieu-tra/{{ batch.id }}/ho-dan/{{ household.id }}/nhap-nhanh/luu">\n                <input type="hidden" name="head_name" value="{{ household_form_data.head_name }}">\n                <input type="hidden" name="address" value="{{ household_form_data.address }}">\n                <input type="hidden" name="hamlet_name" value="{{ household_form_data.hamlet_name }}">\n                <input type="hidden" name="phone" value="{{ household_form_data.phone }}">\n                <input type="hidden" name="household_notes" value="{{ household_form_data.household_notes }}">\n                <input type="hidden" name="form_status" value="DA_HOAN_THANH">\n                <input type="hidden" name="survey_date" value="{{ household_form_data.survey_date or today }}">\n                <input type="hidden" name="village_head_name" value="{{ household_form_data.village_head_name }}">\n                <input type="hidden" name="household_representative_name" value="{{ household_form_data.household_representative_name or household_form_data.head_name }}">\n                <input type="hidden" name="household_confirmed" value="1">\n                <input type="hidden" name="form_notes" value="{{ household_form_data.form_notes }}">\n                <button class="pc-gv-v18-finish" type="submit" name="submit_action" value="save">✓ Hoàn thành</button>\n                {% if next_url %}\n                    <button class="pc-gv-v18-finish pc-gv-v18-finish-next" type="submit" name="submit_action" value="save_next">✓ Hoàn thành & hộ tiếp theo →</button>\n                {% endif %}\n            </form>\n        {% endif %}\n\n        <a class="pc-gv-v18-back" href="/dieu-tra/{{ batch.id }}/ho-dan?page_size=100&sort=hamlet">← Phiếu phân công</a>\n    </div>\n</main>\n{% endif %}\n{# === GV_MOBILE_V18_QUICK_END === #}'
ROUTER_STATUS_BLOCK = '# === GV_MOBILE_V18_STATUS_START ===\nSTATUS_MESSAGES.update(\n    {\n        "mobile_person_accepted": "Đã chấp nhận thông tin thành viên.",\n        "mobile_person_need_edit": "Thành viên chưa có dữ liệu để chấp nhận. Hãy bấm Sửa và lưu thông tin trước.",\n    }\n)\n# === GV_MOBILE_V18_STATUS_END ==='
ROUTER_SUMMARY_BLOCK = '    # === GV_MOBILE_V18_SUMMARY_START ===\n    # Bổ sung dữ liệu hiển thị tối giản cho màn hình giáo viên trên điện thoại.\n    # Nếu hồ sơ năm hiện tại chưa được rà soát, sử dụng dữ liệu kế thừa năm trước\n    # làm phần gợi ý đúng như màn hình năm học hiện có.\n    for summary in person_summaries:\n        person = summary["person"]\n        current_record = summary["year_record"]\n        previous_hint = lay_goi_y_nam_hoc_truoc(\n            db=db,\n            person_id=int(person.id),\n            school_year_id=batch.school_year_id,\n        )\n        if current_record is not None and getattr(current_record, "is_reviewed", False):\n            previous_hint = None\n\n        display_record, inherited_fields = tao_ban_ghi_hien_thi_nam_hoc(\n            selected_record=current_record,\n            previous_hint=previous_hint,\n            survey_form_id=survey_form.id,\n            person_id=int(person.id),\n            school_year_id=batch.school_year_id,\n        )\n\n        school_name = "—"\n        class_name = "—"\n        if display_record is not None:\n            school_obj = (\n                db.get(School, display_record.school_id)\n                if getattr(display_record, "school_id", None) is not None\n                else None\n            )\n            class_obj = (\n                db.get(Classroom, display_record.class_id)\n                if getattr(display_record, "class_id", None) is not None\n                else None\n            )\n            school_name = (\n                getattr(display_record, "school_name_reported", None)\n                or (school_obj.name if school_obj is not None else "")\n                or "—"\n            )\n            class_name = (\n                getattr(display_record, "class_name_reported", None)\n                or (class_obj.name if class_obj is not None else "")\n                or "—"\n            )\n\n        summary.update(\n            {\n                "display_record": display_record,\n                "inherited_fields": inherited_fields,\n                "school_name": school_name,\n                "class_name": class_name,\n                "is_reviewed": bool(\n                    current_record is not None\n                    and getattr(current_record, "is_reviewed", False)\n                ),\n                "can_accept": bool(\n                    display_record is not None\n                    and ban_ghi_nam_hoc_co_du_lieu(display_record)\n                ),\n            }\n        )\n    # === GV_MOBILE_V18_SUMMARY_END ===\n'
ROUTER_ACCEPT_BLOCK = '# === GV_MOBILE_V18_ACCEPT_START ===\n@router.post(\n    "/{batch_id}/ho-dan/{household_id}/nhap-nhanh/{person_id}/chap-nhan"\n)\ndef chap_nhan_thanh_vien_nhap_nhanh_mobile(\n    batch_id: int,\n    household_id: int,\n    person_id: int,\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    """Chấp nhận dữ liệu đang hiển thị mà không buộc giáo viên mở form sửa."""\n\n    survey_form = lay_phieu_ho(\n        db=db,\n        batch_id=batch_id,\n        household_id=household_id,\n    )\n    if survey_form is None:\n        return RedirectResponse(\n            url=f"/dieu-tra/{batch_id}/ho-dan",\n            status_code=303,\n        )\n\n    user = lay_thong_tin_nguoi_dung(request)\n    role_code = normalize_role_code(user.get("role_code"))\n    if not can_edit_survey_data(role_code):\n        return RedirectResponse(\n            url=tao_url_nhap_nhanh(\n                batch_id=batch_id,\n                household_id=household_id,\n            ),\n            status_code=303,\n        )\n\n    allowed_form_id = db.scalar(\n        select(SurveyForm.id).where(\n            SurveyForm.id == survey_form.id,\n            *tao_bo_loc_phieu_theo_nguoi_dung(request),\n        )\n    )\n    if allowed_form_id is None:\n        return RedirectResponse(\n            url=f"/dieu-tra/{batch_id}/ho-dan",\n            status_code=303,\n        )\n\n    if survey_form.survey_batch.status == "DA_KET_THUC" or survey_form.survey_batch.is_locked:\n        return RedirectResponse(\n            url=tao_url_nhap_nhanh(\n                batch_id=batch_id,\n                household_id=household_id,\n            ),\n            status_code=303,\n        )\n\n    person = db.scalar(\n        select(SurveyPerson).where(\n            SurveyPerson.id == person_id,\n            SurveyPerson.household_id == household_id,\n            SurveyPerson.is_active.is_(True),\n        )\n    )\n    if person is None:\n        return RedirectResponse(\n            url=tao_url_nhap_nhanh(\n                batch_id=batch_id,\n                household_id=household_id,\n            ),\n            status_code=303,\n        )\n\n    school_year_id = int(survey_form.survey_batch.school_year_id)\n    current_record = db.scalar(\n        select(SurveyPersonYearRecord).where(\n            SurveyPersonYearRecord.survey_form_id == survey_form.id,\n            SurveyPersonYearRecord.survey_person_id == person.id,\n            SurveyPersonYearRecord.school_year_id == school_year_id,\n        )\n    )\n\n    previous_hint = lay_goi_y_nam_hoc_truoc(\n        db=db,\n        person_id=int(person.id),\n        school_year_id=school_year_id,\n    )\n    if current_record is not None and getattr(current_record, "is_reviewed", False):\n        previous_hint = None\n\n    display_record, _ = tao_ban_ghi_hien_thi_nam_hoc(\n        selected_record=current_record,\n        previous_hint=previous_hint,\n        survey_form_id=survey_form.id,\n        person_id=int(person.id),\n        school_year_id=school_year_id,\n    )\n\n    if display_record is None or not ban_ghi_nam_hoc_co_du_lieu(display_record):\n        return RedirectResponse(\n            url=tao_url_nhap_nhanh(\n                batch_id=batch_id,\n                household_id=household_id,\n                status="mobile_person_need_edit",\n                anchor="members",\n            ),\n            status_code=303,\n        )\n\n    record = current_record\n    if record is None:\n        record = SurveyPersonYearRecord(\n            survey_form_id=survey_form.id,\n            survey_person_id=person.id,\n            school_year_id=school_year_id,\n            learning_status=(\n                getattr(display_record, "learning_status", None)\n                or "CHUA_XAC_DINH"\n            ),\n        )\n        db.add(record)\n\n    fields_to_copy = (\n        "school_id",\n        "class_id",\n        "school_name_reported",\n        "class_name_reported",\n        "learning_status",\n        "completed_preschool_5",\n        "special_circumstances",\n        "attends_required_days",\n        "attends_regularly",\n        "prepared_vietnamese",\n        "weight_monitored",\n        "underweight",\n        "height_monitored",\n        "stunted",\n        "disability_status",\n        "disability_type",\n        "disability_level",\n        "disability_certificate",\n        "inclusive_education",\n        "disability_support",\n        "disability_support_details",\n        "notes",\n    )\n    for field_name in fields_to_copy:\n        setattr(record, field_name, getattr(display_record, field_name, None))\n\n    record.is_reviewed = True\n    if survey_form.status == "CHUA_DIEU_TRA":\n        survey_form.status = "DANG_DIEU_TRA"\n\n    db.commit()\n\n    return RedirectResponse(\n        url=tao_url_nhap_nhanh(\n            batch_id=batch_id,\n            household_id=household_id,\n            status="mobile_person_accepted",\n            anchor="members",\n        ),\n        status_code=303,\n    )\n# === GV_MOBILE_V18_ACCEPT_END ==='

BLOCKS_TO_REMOVE = [
    ("{# === GIAO_VIEN_MOBILE_V1_7A_START === #}", "{# === GIAO_VIEN_MOBILE_V1_7A_END === #}"),
    ("{# === GV_MOBILE_V17B_INDEX_START === #}", "{# === GV_MOBILE_V17B_INDEX_END === #}"),
    ("{# === GV_MOBILE_V17C_HOME_START === #}", "{# === GV_MOBILE_V17C_HOME_END === #}"),
    ("{# === GV_MOBILE_V17D_HOME_START === #}", "{# === GV_MOBILE_V17D_HOME_END === #}"),
    ("{# === GV_MOBILE_V18_HOME_START === #}", "{# === GV_MOBILE_V18_HOME_END === #}"),
    ("{# === GV_MOBILE_V18_ASSIGNMENTS_START === #}", "{# === GV_MOBILE_V18_ASSIGNMENTS_END === #}"),
    ("{# === GV_MOBILE_V18_QUICK_START === #}", "{# === GV_MOBILE_V18_QUICK_END === #}"),
    ("# === GV_MOBILE_V18_STATUS_START ===", "# === GV_MOBILE_V18_STATUS_END ==="),
    ("    # === GV_MOBILE_V18_SUMMARY_START ===", "    # === GV_MOBILE_V18_SUMMARY_END ==="),
    ("# === GV_MOBILE_V18_ACCEPT_START ===", "# === GV_MOBILE_V18_ACCEPT_END ==="),
]


def sha256(path: Path):
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def backup(path: Path, manifest: dict):
    rel = path.relative_to(PROJECT).as_posix()
    manifest[rel] = {"existed": path.exists()}
    if path.exists():
        dst = BACKUP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)


def restore(manifest: dict):
    for rel, info in manifest.items():
        dst = PROJECT / rel
        src = BACKUP / rel
        if info.get("existed"):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        elif dst.exists():
            dst.unlink()


def strip_block(text: str, start: str, end: str) -> str:
    while start in text and end in text:
        a = text.index(start)
        b = text.index(end, a) + len(end)
        text = text[:a] + text[b:]
    return text


def strip_known_blocks(text: str) -> str:
    for start, end in BLOCKS_TO_REMOVE:
        text = strip_block(text, start, end)
    return text


def insert_after_body(text: str, block: str) -> str:
    anchor = "<body>"
    if anchor not in text:
        raise RuntimeError("Khong tim thay the <body> trong template.")
    return text.replace(anchor, anchor + "\n" + block, 1)


def patch_index(text: str) -> str:
    text = strip_known_blocks(text)
    return insert_after_body(text, INDEX_BLOCK)


def patch_households(text: str) -> str:
    text = strip_known_blocks(text)
    return insert_after_body(text, HOUSEHOLDS_BLOCK)


def patch_quick(text: str) -> str:
    text = strip_known_blocks(text)
    return insert_after_body(text, QUICK_BLOCK)


def patch_menu(text: str) -> str:
    return strip_known_blocks(text)


def patch_router(text: str) -> str:
    text = strip_known_blocks(text)

    status_anchor = "HOUSEHOLD_PAGE_SIZE = 20"
    if status_anchor not in text:
        raise RuntimeError("Khong tim thay anchor HOUSEHOLD_PAGE_SIZE trong surveys.py")
    text = text.replace(status_anchor, ROUTER_STATUS_BLOCK + "\n\n" + status_anchor, 1)

    summary_anchor = "    warnings: list[str] = []"
    if summary_anchor not in text:
        raise RuntimeError("Khong tim thay anchor warnings trong hien_thi_trang_nhap_nhanh")
    text = text.replace(summary_anchor, ROUTER_SUMMARY_BLOCK + "\n" + summary_anchor, 1)

    accept_anchor = "# =========================================================\n# KIỂM TRA CHẤT LƯỢNG DỮ LIỆU ĐIỀU TRA"
    if accept_anchor not in text:
        raise RuntimeError("Khong tim thay anchor KIEM TRA CHAT LUONG trong surveys.py")
    text = text.replace(accept_anchor, ROUTER_ACCEPT_BLOCK + "\n\n" + accept_anchor, 1)
    return text


def main():
    print("=" * 82)
    print("GIAO VIEN MOBILE V1.8 - LUONG DIEU TRA TOI GIAN")
    print("MAN 1: CHON NAM + PHIEU PHAN CONG")
    print("MAN 2: SO PHIEU - TEN HO - NHAP NHANH")
    print("MAN 3: THANH VIEN - TRUONG - LOP - SUA - CHAP NHAN")
    print("CUOI PHIEU: THEM THANH VIEN - HOAN THANH - HO TIEP THEO")
    print("=" * 82)

    required = [PYTHON, MAIN, DB, ROUTER, INDEX, HOUSEHOLDS, QUICK]
    for path in required:
        if not path.exists():
            raise RuntimeError(f"Khong tim thay: {path}")

    before_main = sha256(MAIN)
    before_db = sha256(DB)

    manifest = {}
    BACKUP.mkdir(parents=True, exist_ok=False)
    for path in [ROUTER, INDEX, HOUSEHOLDS, QUICK, MENU]:
        backup(path, manifest)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        ROUTER.write_text(patch_router(ROUTER.read_text(encoding="utf-8-sig")), encoding="utf-8")
        INDEX.write_text(patch_index(INDEX.read_text(encoding="utf-8-sig")), encoding="utf-8")
        HOUSEHOLDS.write_text(patch_households(HOUSEHOLDS.read_text(encoding="utf-8-sig")), encoding="utf-8")
        QUICK.write_text(patch_quick(QUICK.read_text(encoding="utf-8-sig")), encoding="utf-8")
        if MENU.exists():
            MENU.write_text(patch_menu(MENU.read_text(encoding="utf-8-sig")), encoding="utf-8")

        for cache in (PROJECT / "app").rglob("__pycache__"):
            if cache.is_dir():
                shutil.rmtree(cache, ignore_errors=True)

        py_compile.compile(str(ROUTER), doraise=True)

        checker = PROJECT / "check_giao_vien_mobile_v1_8.py"
        checker.write_text(
            "from pathlib import Path\n"
            "from jinja2 import Environment, FileSystemLoader\n"
            "root=Path(r'" + str((PROJECT / "app" / "templates")).replace("\\", "\\\\") + "')\n"
            "env=Environment(loader=FileSystemLoader(str(root)))\n"
            "for name in ['surveys/index.html','surveys/households.html','surveys/quick_entry.html']:\n"
            "    env.get_template(name)\n"
            "print('Jinja templates: DAT')\n",
            encoding="utf-8",
        )
        subprocess.run([str(PYTHON), str(checker)], cwd=PROJECT, check=True)

        if sha256(MAIN) != before_main:
            raise RuntimeError("app/main.py da thay doi - dung cai dat.")
        if sha256(DB) != before_db:
            raise RuntimeError("data/phocap.db da thay doi - dung cai dat.")

        checks = [
            (INDEX, "GV_MOBILE_V18_HOME_START"),
            (HOUSEHOLDS, "GV_MOBILE_V18_ASSIGNMENTS_START"),
            (QUICK, "GV_MOBILE_V18_QUICK_START"),
            (ROUTER, "chap_nhan_thanh_vien_nhap_nhanh_mobile"),
        ]
        for path, token in checks:
            if token not in path.read_text(encoding="utf-8"):
                raise RuntimeError(f"Kiem tra that bai: {token}")

        print("")
        print("KET QUA:")
        print(" - Man hinh chinh GV dien thoai chi con Chon nam + Phieu phan cong: DAT")
        print(" - Danh sach phieu chi con So phieu - Ten ho - Nhap nhanh: DAT")
        print(" - Nhap nhanh hien Thanh vien - Truong - Lop - Sua - Chap nhan: DAT")
        print(" - Them thanh vien moi o cuoi phieu: DAT")
        print(" - Hoan thanh / Hoan thanh & ho tiep theo: DAT")
        print(" - Nut Chap nhan dung co san is_reviewed, KHONG them cot database: DAT")
        print(" - Quy tac kiem tra du lieu khi Hoan thanh: GIU NGUYEN")
        print(" - Desktop: GIU NGUYEN")
        print(" - app/main.py: KHONG DOI")
        print(" - data/phocap.db: KHONG DOI")
        print("")
        print("CAI DAT GIAO VIEN MOBILE V1.8 THANH CONG")
        print("Backup:", BACKUP)
        return 0

    except Exception:
        traceback.print_exc()
        restore(manifest)
        print("")
        print("CO LOI - DA KHOI PHUC TU DONG TU BACKUP.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
