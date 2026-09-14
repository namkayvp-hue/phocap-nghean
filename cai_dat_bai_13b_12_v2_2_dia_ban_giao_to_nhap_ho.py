# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment

PROJECT = Path(r"C:\PhoCap")
APP = PROJECT / "app"
DB = PROJECT / "data" / "phocap.db"
EXPORTS = PROJECT / "exports"

MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
HOUSEHOLDS_TEMPLATE = APP / "templates" / "surveys" / "households.html"
AREA_TEMPLATE_PATH = APP / "templates" / "survey_teams" / "commune_areas_v2_2.html"
NEW_HOUSE_TEMPLATE_PATH = APP / "templates" / "surveys" / "new_household_team_v2_2.html"
SURVEYS = APP / "routers" / "surveys.py"
TEAM_ROUTER = APP / "routers" / "survey_team_registration.py"
ACCESS = APP / "access_control.py"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = EXPORTS / f"backup_bai_13b_12_v2_2_{STAMP}"
DB_BACKUP = BACKUP / "phocap.db"
REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_2_{STAMP}.txt"

MARK_MENU = "BAI_13B_12_V2_2_MENU_AREA"
MARK_HIDE_UPDATE = "BAI_13B_12_V2_2_HIDE_UPDATE_XA"
MARK_SURVEY_SCOPE = "BAI_13B_12_V2_2_TEACHER_BATCH_SCOPE"
MARK_ACCESS = "BAI_13B_12_V2_2_ACCESS"
MARK_HOUSE_BUTTON = "BAI_13B_12_V2_2_NEW_HOUSE_BUTTON"
MARK_FINALIZE = "BAI_13B_12_V2_2_FINALIZE_WITH_AREA"

AREA_TEMPLATE = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Danh mục địa bàn điều tra</title>\n<style>\n*{box-sizing:border-box}\nbody{margin:0;background:#f4f7fb;color:#24384b;font-family:"Segoe UI",Arial,sans-serif}\n.b1322-wrap{width:min(1500px,calc(100% - 28px));margin:22px auto 48px}\n.b1322-head{background:linear-gradient(135deg,#0b5fa9,#1579d3);color:#fff;border-radius:16px;padding:20px 22px;margin-bottom:18px}\n.b1322-head h1{margin:0 0 7px;font-size:27px}.b1322-head p{margin:0;line-height:1.5;opacity:.95}\n.b1322-note,.b1322-alert{padding:13px 15px;border-radius:11px;margin:14px 0;line-height:1.5}\n.b1322-note{background:#edf7ff;border:1px solid #b6d8f4;color:#28506f}\n.b1322-alert{background:#fff8e7;border:1px solid #ecd38b;color:#705618}\n.b1322-ok{background:#eef9f0;border-color:#a9d6b0;color:#286238}\n.b1322-panel{background:#fff;border:1px solid #dce6ef;border-radius:15px;padding:18px;margin-bottom:18px;box-shadow:0 7px 24px rgba(30,57,81,.06)}\n.b1322-panel h2{margin:0 0 14px;font-size:21px}\n.b1322-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}\n.b1322-field{display:flex;flex-direction:column;gap:6px}\n.b1322-field.wide{grid-column:span 2}\n.b1322-field label{font-weight:800;font-size:13px;color:#34526e}\n.b1322-field input,.b1322-field select,.b1322-field textarea{width:100%;border:1px solid #cbd8e4;border-radius:9px;padding:10px 11px;font:inherit;background:#fff}\n.b1322-actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-top:14px}\n.b1322-btn{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:0 13px;border:0;border-radius:9px;text-decoration:none;font-weight:800;cursor:pointer;font-size:14px}\n.b1322-primary{background:#0b6dc6;color:#fff}.b1322-secondary{background:#eef3f7;color:#31506d}.b1322-danger{background:#fff0f0;color:#9b2020;border:1px solid #ecc3c3}\n.b1322-table-wrap{overflow:auto;border:1px solid #e0e8ef;border-radius:12px}\ntable{width:100%;border-collapse:collapse;min-width:900px;background:#fff}\nth,td{border-bottom:1px solid #e7edf2;padding:10px 9px;text-align:left;vertical-align:top}\nth{background:#f4f8fb;font-size:12px;text-transform:uppercase;color:#47627a;position:sticky;top:0;z-index:1}\ntd.num,th.num{text-align:right}.muted{color:#758798;font-size:12px}.nowrap{white-space:nowrap}\n.badge{display:inline-flex;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:800;background:#edf3f7}\n.badge.off{background:#f3f3f3;color:#777}.progress{height:7px;background:#e8eef4;border-radius:999px;overflow:hidden;margin-top:5px}.progress>span{display:block;height:100%;background:#0b6dc6}\n.assignment-input{width:82px!important;text-align:right;padding:8px!important}\n.team-head{min-width:150px}.team-members{font-size:11px;font-weight:500;line-height:1.35;text-transform:none;margin-top:4px;color:#687d90}\n.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:12px 0}\n.stat{background:#f7fafc;border:1px solid #e0e9f0;border-radius:12px;padding:13px}.stat small{color:#6b7f91;font-weight:700}.stat strong{display:block;font-size:23px;margin-top:4px}\n@media(max-width:900px){.b1322-grid{grid-template-columns:1fr 1fr}.b1322-field.wide{grid-column:span 2}.stats{grid-template-columns:1fr 1fr}}\n@media(max-width:600px){.b1322-grid{grid-template-columns:1fr}.b1322-field.wide{grid-column:auto}.stats{grid-template-columns:1fr 1fr}}\n</style>\n</head>\n<body>\n{% include "partials/dropdown_menu_v1.html" %}\n<main class="b1322-wrap">\n<section class="b1322-head">\n  <h1>Danh mục thôn/xóm/khối/tổ/bản</h1>\n  <p>Xã/phường khai báo địa bàn và số hộ dự kiến. Xã không nhập hộ dân; tổ điều tra được giao địa bàn mới trực tiếp tạo hộ ngoài thực địa.</p>\n</section>\n\n{% if message %}\n<div class="b1322-alert {% if message_kind == \'ok\' %}b1322-ok{% endif %}">{{ message }}</div>\n{% endif %}\n\n<section class="b1322-panel">\n<h2>1. Chọn năm học</h2>\n<form method="get" action="/dieu-tra/phan-cong-to-dieu-tra/dia-ban">\n<div class="b1322-grid">\n<div class="b1322-field">\n<label>Năm học</label>\n<select name="school_year_id" onchange="this.form.submit()">\n{% for year in years %}\n<option value="{{ year.id }}" {% if selected_year and year.id == selected_year.id %}selected{% endif %}>{{ year.code }}{% if year.is_active %} · đang hoạt động{% endif %}</option>\n{% endfor %}\n</select>\n</div>\n{% if batches %}\n<div class="b1322-field wide">\n<label>Đợt điều tra dùng để giao địa bàn cho tổ</label>\n<select name="batch_id" onchange="this.form.submit()">\n<option value="">-- Chọn đợt điều tra --</option>\n{% for b in batches %}\n<option value="{{ b.id }}" {% if selected_batch and b.id == selected_batch.id %}selected{% endif %}>{{ b.code }} · {{ b.name }}</option>\n{% endfor %}\n</select>\n</div>\n{% else %}\n<div class="b1322-field wide">\n<label>Đợt điều tra</label>\n<div class="b1322-note" style="margin:0">Năm học này chưa có đợt điều tra của xã/phường. Có thể khai báo danh mục địa bàn trước; sau khi Sở khởi tạo đợt, quay lại để giao địa bàn/chỉ tiêu cho tổ.</div>\n</div>\n{% endif %}\n</div>\n</form>\n</section>\n\n<section class="b1322-panel">\n<h2>2. Khai báo địa bàn và số hộ dự kiến</h2>\n<form method="post" action="/dieu-tra/phan-cong-to-dieu-tra/dia-ban/luu" id="area-form">\n<input type="hidden" name="school_year_id" value="{{ selected_year.id if selected_year else \'\' }}">\n<input type="hidden" name="batch_id" value="{{ selected_batch.id if selected_batch else \'\' }}">\n<input type="hidden" name="area_id" id="area_id" value="">\n<div class="b1322-grid">\n<div class="b1322-field">\n<label>Loại địa bàn *</label>\n<select name="area_type" id="area_type" required>\n<option value="THON">Thôn</option><option value="XOM">Xóm</option><option value="KHOI">Khối</option><option value="TO">Tổ</option><option value="BAN">Bản</option>\n</select>\n</div>\n<div class="b1322-field wide"><label>Tên địa bàn *</label><input name="name" id="area_name" maxlength="200" required placeholder="Ví dụ: Xóm 1"></div>\n<div class="b1322-field"><label>Số hộ dự kiến *</label><input name="expected_households" id="expected_households" type="number" min="0" step="1" required value="0"></div>\n<div class="b1322-field"><label>Ghi chú</label><input name="notes" id="area_notes" maxlength="500"></div>\n</div>\n<div class="b1322-actions">\n<button class="b1322-btn b1322-primary" type="submit">💾 Lưu địa bàn</button>\n<button class="b1322-btn b1322-secondary" type="button" onclick="b1322ResetArea()">Nhập địa bàn mới</button>\n</div>\n</form>\n\n<div class="stats">\n<div class="stat"><small>Số địa bàn đang dùng</small><strong>{{ area_summary.active_count }}</strong></div>\n<div class="stat"><small>Tổng hộ dự kiến</small><strong>{{ area_summary.expected_total }}</strong></div>\n<div class="stat"><small>Hộ đã nhập thực tế</small><strong>{{ area_summary.actual_total }}</strong></div>\n<div class="stat"><small>Còn thiếu</small><strong>{{ area_summary.remaining_total }}</strong></div>\n</div>\n\n<div class="b1322-table-wrap">\n<table>\n<thead><tr><th>Loại</th><th>Địa bàn</th><th class="num">Hộ dự kiến</th><th class="num">Đã nhập</th><th class="num">Còn thiếu</th><th>Tiến độ</th><th>Trạng thái</th><th>Thao tác</th></tr></thead>\n<tbody>\n{% for a in areas %}\n<tr>\n<td><span class="badge">{{ a.area_type_label }}</span></td>\n<td><strong>{{ a.name }}</strong>{% if a.notes %}<div class="muted">{{ a.notes }}</div>{% endif %}</td>\n<td class="num">{{ a.expected_households }}</td>\n<td class="num">{{ a.actual_households }}</td>\n<td class="num">{{ a.remaining_households }}</td>\n<td style="min-width:130px"><strong>{{ a.progress_percent }}%</strong><div class="progress"><span style="width:{{ a.progress_percent }}%"></span></div></td>\n<td>{% if a.is_active %}<span class="badge">Đang dùng</span>{% else %}<span class="badge off">Ngừng dùng</span>{% endif %}</td>\n<td class="nowrap">\n{% if a.is_active %}\n<button type="button" class="b1322-btn b1322-secondary"\n onclick=\'b1322EditArea({{ a.id }}, {{ a.area_type|tojson }}, {{ a.name|tojson }}, {{ a.expected_households }}, {{ (a.notes or "")|tojson }})\'>Sửa</button>\n<form method="post" action="/dieu-tra/phan-cong-to-dieu-tra/dia-ban/ngung-dung" style="display:inline">\n<input type="hidden" name="area_id" value="{{ a.id }}"><input type="hidden" name="school_year_id" value="{{ selected_year.id if selected_year else \'\' }}"><input type="hidden" name="batch_id" value="{{ selected_batch.id if selected_batch else \'\' }}">\n<button class="b1322-btn b1322-danger" type="submit">Ngừng dùng</button>\n</form>\n{% else %}\n<form method="post" action="/dieu-tra/phan-cong-to-dieu-tra/dia-ban/kich-hoat" style="display:inline">\n<input type="hidden" name="area_id" value="{{ a.id }}"><input type="hidden" name="school_year_id" value="{{ selected_year.id if selected_year else \'\' }}"><input type="hidden" name="batch_id" value="{{ selected_batch.id if selected_batch else \'\' }}">\n<button class="b1322-btn b1322-secondary" type="submit">Kích hoạt lại</button>\n</form>\n{% endif %}\n</td>\n</tr>\n{% else %}\n<tr><td colspan="8" class="muted">Chưa khai báo địa bàn nào.</td></tr>\n{% endfor %}\n</tbody>\n</table>\n</div>\n</section>\n\n<section class="b1322-panel">\n<h2>3. Giao địa bàn và chỉ tiêu số hộ cho tổ điều tra</h2>\n{% if not selected_batch %}\n<div class="b1322-note">Chọn một đợt điều tra ở mục 1 để giao địa bàn/chỉ tiêu cho các tổ.</div>\n{% elif not teams %}\n<div class="b1322-note">Đợt này chưa có tổ điều tra. Hãy nhận danh sách giáo viên từ các trường và ghép tổ 3 cấp trước.</div>\n{% else %}\n{% if teams_locked %}\n<div class="b1322-alert">Các tổ của đợt này đã được chốt/gửi. Danh sách địa bàn và chỉ tiêu được khóa để bảo toàn nhiệm vụ đã giao.</div>\n{% else %}\n<div class="b1322-actions">\n<form method="post" action="/dieu-tra/phan-cong-to-dieu-tra/dia-ban/chia-deu">\n<input type="hidden" name="batch_id" value="{{ selected_batch.id }}">\n<input type="hidden" name="school_year_id" value="{{ selected_year.id }}">\n<button class="b1322-btn b1322-secondary" type="submit">⚖️ Chia đều tự động theo số hộ dự kiến</button>\n</form>\n</div>\n{% endif %}\n\n<form method="post" action="/dieu-tra/phan-cong-to-dieu-tra/dia-ban/phan-cong-luu">\n<input type="hidden" name="batch_id" value="{{ selected_batch.id }}">\n<input type="hidden" name="school_year_id" value="{{ selected_year.id }}">\n<div class="b1322-table-wrap" style="margin-top:12px">\n<table>\n<thead>\n<tr><th>Địa bàn</th><th class="num">Dự kiến</th><th class="num">Đã nhập</th><th class="num">Đã giao</th>\n{% for team in teams %}\n<th class="team-head">Tổ {{ team.team_number }}<div class="team-members">{{ team.members_text }}</div><div class="muted">Tổng giao: {{ team.assigned_quota }} · Đã nhập: {{ team.actual_count }}</div></th>\n{% endfor %}\n</tr>\n</thead>\n<tbody>\n{% for a in active_areas %}\n<tr>\n<td><strong>{{ a.area_type_label }} {{ a.name }}</strong></td>\n<td class="num">{{ a.expected_households }}</td>\n<td class="num">{{ a.actual_households }}</td>\n<td class="num">{{ a.assigned_quota_selected }}</td>\n{% for team in teams %}\n<td><input class="assignment-input" type="number" min="0" step="1"\n name="quota__{{ team.id }}__{{ a.id }}"\n value="{{ assignment_values.get((team.id|string) ~ \':\' ~ (a.id|string), 0) }}"\n {% if teams_locked %}disabled{% endif %}></td>\n{% endfor %}\n</tr>\n{% endfor %}\n</tbody>\n</table>\n</div>\n{% if not teams_locked %}\n<div class="b1322-actions"><button class="b1322-btn b1322-primary" type="submit">💾 Lưu giao địa bàn/chỉ tiêu</button></div>\n{% endif %}\n</form>\n<div class="b1322-note">\n<strong>Điều kiện để Chốt/Gửi tổ:</strong> mỗi tổ phải có chỉ tiêu lớn hơn 0 và tổng chỉ tiêu giao của từng địa bàn phải đúng bằng số hộ dự kiến của địa bàn đó. Sau khi chốt, tổ mới được tạo hộ ngoài thực địa.\n</div>\n{% endif %}\n</section>\n</main>\n<script>\nfunction b1322ResetArea(){\n document.getElementById("area_id").value="";\n document.getElementById("area_type").value="THON";\n document.getElementById("area_name").value="";\n document.getElementById("expected_households").value="0";\n document.getElementById("area_notes").value="";\n document.getElementById("area_name").focus();\n}\nfunction b1322EditArea(id,type,name,expected,notes){\n document.getElementById("area_id").value=id;\n document.getElementById("area_type").value=type;\n document.getElementById("area_name").value=name;\n document.getElementById("expected_households").value=expected;\n document.getElementById("area_notes").value=notes||"";\n document.getElementById("area-form").scrollIntoView({behavior:"smooth",block:"center"});\n}\n</script>\n</body>\n</html>\n'
NEW_HOUSE_TEMPLATE = '<!DOCTYPE html>\n<html lang="vi">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>Điều tra mới – Nhập hộ dân mới</title>\n<style>\n*{box-sizing:border-box}body{margin:0;background:#f3f6fa;font-family:"Segoe UI",Arial,sans-serif;color:#24384b}\n.wrap{width:min(860px,calc(100% - 24px));margin:18px auto 40px}.head{background:linear-gradient(135deg,#0b5fa9,#1579d3);color:#fff;border-radius:15px;padding:18px;margin-bottom:16px}.head h1{margin:0 0 7px;font-size:25px}.head p{margin:0;line-height:1.45}\n.card{background:#fff;border:1px solid #dbe5ed;border-radius:14px;padding:17px;margin-bottom:14px}.notice{background:#edf7ff;border:1px solid #b7d9f5;padding:12px 14px;border-radius:10px;color:#28506f;line-height:1.5}\n.team{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.member{background:#f7fafc;border:1px solid #e0e9f0;border-radius:10px;padding:10px}.member small{display:block;color:#738596}\n.area{display:block;border:1px solid #d7e3ed;border-radius:11px;padding:12px;margin:9px 0;cursor:pointer}.area:hover{border-color:#0b6dc6}.area input{margin-right:7px}.area strong{font-size:16px}.stats{font-size:12px;color:#667e92;margin-top:5px}\n.field{display:flex;flex-direction:column;gap:6px;margin:12px 0}.field label{font-weight:800}.field input,.field textarea{border:1px solid #cbd8e4;border-radius:9px;padding:11px;font:inherit;width:100%}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:17px}.btn{border:0;border-radius:9px;min-height:43px;padding:0 15px;font-weight:800;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}.primary{background:#0b6dc6;color:#fff}.secondary{background:#edf2f6;color:#31506d}\n.alert{background:#fff4e8;border:1px solid #efc990;color:#785019;padding:12px 14px;border-radius:10px;margin-bottom:13px}\n@media(max-width:620px){.team{grid-template-columns:1fr}.head h1{font-size:21px}}\n</style>\n</head>\n<body>\n{% include "partials/dropdown_menu_v1.html" %}\n<main class="wrap">\n<section class="head">\n<h1>➕ Điều tra mới – Nhập hộ dân mới</h1>\n<p>{{ batch.name }} · Tổ {{ team.team_number }} · {{ batch.school_year.code }}</p>\n</section>\n{% if message %}<div class="alert">{{ message }}</div>{% endif %}\n<div class="notice"><strong>Dữ liệu thực tế mới:</strong> chỉ nhập hộ đang điều tra ngoài thực địa. Không lấy địa chỉ, trường/lớp hoặc tình trạng học tập năm 2025-2026 làm dữ liệu hiện tại. Sau khi tạo hộ, hệ thống chuyển thẳng sang Nhập nhanh để nhập toàn bộ thành viên và trình độ.</div>\n\n<section class="card">\n<h2 style="margin-top:0">Tổ điều tra 3 cấp</h2>\n<div class="team">\n{% for m in members %}\n<div class="member"><strong>{{ m.full_name }}</strong><small>{{ m.level_code }} · {{ m.school_name }}</small></div>\n{% endfor %}\n</div>\n</section>\n\n<section class="card">\n<h2 style="margin-top:0">Hộ dân mới</h2>\n<form method="post" action="/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/{{ batch.id }}/them" autocomplete="off">\n<label style="font-weight:800">Chọn địa bàn được giao *</label>\n{% for a in assignments %}\n<label class="area">\n<input type="radio" name="area_id" value="{{ a.area_id }}" {% if loop.first %}checked{% endif %} required>\n<strong>{{ a.area_type_label }} {{ a.area_name }}</strong>\n<div class="stats">Chỉ tiêu của tổ: {{ a.household_quota }} hộ · Đã nhập: {{ a.actual_count }} · Còn: {{ a.remaining_count }}</div>\n</label>\n{% else %}\n<div class="alert">Tổ không còn địa bàn/chỉ tiêu để nhập hộ mới.</div>\n{% endfor %}\n\n<div class="field"><label>Họ và tên chủ hộ *</label><input name="head_name" maxlength="200" required autofocus></div>\n<div class="field"><label>Địa chỉ chi tiết hiện tại *</label><textarea name="address" rows="3" required placeholder="Số nhà/đường/ngõ hoặc mô tả vị trí thực tế"></textarea></div>\n<div class="field"><label>Điện thoại liên hệ</label><input name="phone" maxlength="30" inputmode="tel"></div>\n<div class="field"><label>Ghi chú</label><textarea name="notes" rows="2"></textarea></div>\n<div class="actions">\n{% if assignments %}\n<button class="btn primary" type="submit">Lưu hộ và bắt đầu nhập thành viên</button>\n{% endif %}\n<a class="btn secondary" href="/dieu-tra/{{ batch.id }}/ho-dan">Quay lại danh sách</a>\n</div>\n</form>\n</section>\n</main>\n</body>\n</html>\n'
AREA_ROUTER_BLOCK = '\n# ============================================================\n# BAI_13B_12_V2_2_AREA_WORKFLOW_START\n# Danh mục địa bàn + giao địa bàn/chỉ tiêu cho tổ điều tra.\n# ============================================================\nfrom datetime import datetime as _b1322_datetime\n\n_B1322_AREA_TYPES = {\n    "THON": "Thôn",\n    "XOM": "Xóm",\n    "KHOI": "Khối",\n    "TO": "Tổ",\n    "BAN": "Bản",\n}\n\n_B1322_SCHEMA_SQL = (\n    """\n    CREATE TABLE IF NOT EXISTS survey_commune_areas (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        commune_id INTEGER NOT NULL,\n        school_year_id INTEGER NOT NULL,\n        code VARCHAR(80) NOT NULL,\n        name VARCHAR(200) NOT NULL,\n        area_type VARCHAR(20) NOT NULL,\n        expected_households INTEGER NOT NULL DEFAULT 0,\n        notes TEXT NULL,\n        is_active BOOLEAN NOT NULL DEFAULT 1,\n        created_by_user_id INTEGER NULL,\n        created_at DATETIME NOT NULL,\n        updated_at DATETIME NOT NULL,\n        UNIQUE(commune_id, school_year_id, code),\n        FOREIGN KEY(commune_id) REFERENCES communes(id),\n        FOREIGN KEY(school_year_id) REFERENCES school_years(id),\n        FOREIGN KEY(created_by_user_id) REFERENCES users(id)\n    )\n    """,\n    """\n    CREATE UNIQUE INDEX IF NOT EXISTS\n    uq_survey_commune_areas_name\n    ON survey_commune_areas(\n        commune_id,\n        school_year_id,\n        area_type,\n        name COLLATE NOCASE\n    )\n    """,\n    """\n    CREATE TABLE IF NOT EXISTS survey_team_area_assignments (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        team_id INTEGER NOT NULL,\n        area_id INTEGER NOT NULL,\n        household_quota INTEGER NOT NULL DEFAULT 0,\n        notes TEXT NULL,\n        created_by_user_id INTEGER NULL,\n        created_at DATETIME NOT NULL,\n        updated_at DATETIME NOT NULL,\n        UNIQUE(team_id, area_id),\n        FOREIGN KEY(team_id)\n            REFERENCES survey_investigation_teams(id)\n            ON DELETE CASCADE,\n        FOREIGN KEY(area_id)\n            REFERENCES survey_commune_areas(id),\n        FOREIGN KEY(created_by_user_id)\n            REFERENCES users(id)\n    )\n    """,\n    """\n    CREATE INDEX IF NOT EXISTS\n    ix_survey_team_area_assignments_area\n    ON survey_team_area_assignments(area_id)\n    """,\n    """\n    CREATE TABLE IF NOT EXISTS survey_form_areas (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        survey_form_id INTEGER NOT NULL UNIQUE,\n        area_id INTEGER NOT NULL,\n        created_at DATETIME NOT NULL,\n        FOREIGN KEY(survey_form_id)\n            REFERENCES survey_forms(id),\n        FOREIGN KEY(area_id)\n            REFERENCES survey_commune_areas(id)\n    )\n    """,\n    """\n    CREATE INDEX IF NOT EXISTS\n    ix_survey_form_areas_area\n    ON survey_form_areas(area_id)\n    """,\n)\n\n\ndef _b1322_ensure_area_schema(db: Session) -> None:\n    for statement in _B1322_SCHEMA_SQL:\n        db.execute(text(statement))\n    db.commit()\n\n\ndef _b1322_int(value, default=0):\n    try:\n        return int(str(value or "").strip())\n    except (TypeError, ValueError):\n        return default\n\n\ndef _b1322_redirect(*, school_year_id=None, batch_id=None, status=None):\n    params = []\n    if school_year_id:\n        params.append(f"school_year_id={int(school_year_id)}")\n    if batch_id:\n        params.append(f"batch_id={int(batch_id)}")\n    if status:\n        params.append(f"status={status}")\n    suffix = ("?" + "&".join(params)) if params else ""\n    return RedirectResponse(\n        url="/dieu-tra/phan-cong-to-dieu-tra/dia-ban" + suffix,\n        status_code=303,\n    )\n\n\ndef _b1322_area_messages(status):\n    messages = {\n        "saved": ("ok", "Đã lưu địa bàn."),\n        "duplicate": ("error", "Tên địa bàn đã tồn tại trong cùng loại và năm học."),\n        "invalid": ("error", "Dữ liệu địa bàn chưa hợp lệ."),\n        "locked": ("error", "Địa bàn đã gắn với nhiệm vụ đã chốt/gửi nên không thể thay đổi."),\n        "deactivated": ("ok", "Đã ngừng sử dụng địa bàn."),\n        "activated": ("ok", "Đã kích hoạt lại địa bàn."),\n        "assign_saved": ("ok", "Đã lưu giao địa bàn/chỉ tiêu cho các tổ."),\n        "distributed": ("ok", "Đã chia đều chỉ tiêu theo số hộ dự kiến."),\n        "over_expected": ("error", "Tổng chỉ tiêu giao cho một địa bàn vượt số hộ dự kiến."),\n        "no_teams": ("error", "Chưa có tổ điều tra để giao địa bàn."),\n        "no_areas": ("error", "Chưa có địa bàn đang hoạt động có số hộ dự kiến."),\n        "team_locked": ("error", "Tổ đã chốt/gửi; không thể thay đổi chỉ tiêu."),\n    }\n    return messages.get(str(status or ""), (None, None))\n\n\n@router.get("/dia-ban", response_class=HTMLResponse)\ndef b1322_commune_area_page(\n    request: Request,\n    school_year_id: str | None = None,\n    batch_id: str | None = None,\n    status: str | None = None,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n\n    _b1322_ensure_area_schema(db)\n    user = _user(request)\n    commune_id = _b1322_int(user.get("commune_id"))\n    if not commune_id:\n        return _forbidden()\n\n    years = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT id, code, name, is_active\n                FROM school_years\n                ORDER BY code DESC, id DESC\n                """\n            )\n        ).mappings().all()\n    ]\n\n    selected_year_id = _b1322_int(school_year_id)\n    if not selected_year_id and years:\n        active = next(\n            (item for item in years if bool(item.get("is_active"))),\n            None,\n        )\n        selected_year_id = int(\n            (active or years[0])["id"]\n        )\n\n    selected_year = next(\n        (\n            item for item in years\n            if int(item["id"]) == int(selected_year_id)\n        ),\n        None,\n    )\n\n    batches = []\n    if selected_year is not None:\n        batches = [\n            dict(row)\n            for row in db.execute(\n                text(\n                    """\n                    SELECT id, code, name, status, is_locked\n                    FROM survey_batches\n                    WHERE commune_id = :commune_id\n                      AND school_year_id = :school_year_id\n                    ORDER BY created_at DESC, id DESC\n                    """\n                ),\n                {\n                    "commune_id": commune_id,\n                    "school_year_id": int(selected_year["id"]),\n                },\n            ).mappings().all()\n        ]\n\n    selected_batch_id = _b1322_int(batch_id)\n    selected_batch = next(\n        (\n            item for item in batches\n            if int(item["id"]) == int(selected_batch_id)\n        ),\n        None,\n    )\n\n    areas = []\n    if selected_year is not None:\n        rows = db.execute(\n            text(\n                """\n                SELECT\n                    a.id,\n                    a.code,\n                    a.name,\n                    a.area_type,\n                    a.expected_households,\n                    a.notes,\n                    a.is_active,\n                    COALESCE(\n                        (\n                            SELECT COUNT(*)\n                            FROM survey_form_areas fa\n                            JOIN survey_forms sf\n                              ON sf.id = fa.survey_form_id\n                            JOIN survey_batches sb\n                              ON sb.id = sf.survey_batch_id\n                            WHERE fa.area_id = a.id\n                              AND sb.commune_id = a.commune_id\n                              AND sb.school_year_id = a.school_year_id\n                        ),\n                        0\n                    ) AS actual_households\n                FROM survey_commune_areas a\n                WHERE a.commune_id = :commune_id\n                  AND a.school_year_id = :school_year_id\n                ORDER BY\n                    a.is_active DESC,\n                    a.area_type,\n                    a.name COLLATE NOCASE,\n                    a.id\n                """\n            ),\n            {\n                "commune_id": commune_id,\n                "school_year_id": int(selected_year["id"]),\n            },\n        ).mappings().all()\n\n        for row in rows:\n            item = dict(row)\n            expected = max(\n                0,\n                _b1322_int(item.get("expected_households")),\n            )\n            actual = max(\n                0,\n                _b1322_int(item.get("actual_households")),\n            )\n            item["area_type_label"] = _B1322_AREA_TYPES.get(\n                str(item.get("area_type") or ""),\n                str(item.get("area_type") or ""),\n            )\n            item["remaining_households"] = max(0, expected - actual)\n            item["progress_percent"] = (\n                min(100, round(actual * 100 / expected))\n                if expected\n                else 0\n            )\n            item["assigned_quota_selected"] = 0\n            areas.append(item)\n\n    teams = []\n    assignment_values = {}\n    teams_locked = False\n\n    if selected_batch is not None:\n        team_rows = db.execute(\n            text(\n                """\n                SELECT id, team_number, status\n                FROM survey_investigation_teams\n                WHERE survey_batch_id = :batch_id\n                ORDER BY team_number\n                """\n            ),\n            {"batch_id": int(selected_batch["id"])},\n        ).mappings().all()\n\n        for row in team_rows:\n            team = dict(row)\n            member_rows = db.execute(\n                text(\n                    """\n                    SELECT\n                        tm.level_code,\n                        u.full_name,\n                        COALESCE(s.name, \'\') AS school_name\n                    FROM survey_investigation_team_members tm\n                    JOIN users u ON u.id = tm.user_id\n                    LEFT JOIN schools s ON s.id = tm.school_id\n                    WHERE tm.team_id = :team_id\n                    ORDER BY tm.order_number\n                    """\n                ),\n                {"team_id": int(team["id"])},\n            ).mappings().all()\n\n            team["members_text"] = " · ".join(\n                f"{m[\'level_code\']}: {m[\'full_name\']}"\n                for m in member_rows\n            )\n\n            team["assigned_quota"] = _b1322_int(\n                db.execute(\n                    text(\n                        """\n                        SELECT COALESCE(SUM(household_quota), 0)\n                        FROM survey_team_area_assignments\n                        WHERE team_id = :team_id\n                        """\n                    ),\n                    {"team_id": int(team["id"])},\n                ).scalar()\n            )\n\n            team["actual_count"] = _b1322_int(\n                db.execute(\n                    text(\n                        """\n                        SELECT COUNT(*)\n                        FROM survey_investigation_team_forms tf\n                        WHERE tf.team_id = :team_id\n                        """\n                    ),\n                    {"team_id": int(team["id"])},\n                ).scalar()\n            )\n\n            teams.append(team)\n\n        teams_locked = any(\n            str(team.get("status") or "") != "DRAFT"\n            for team in teams\n        )\n\n        assignment_rows = db.execute(\n            text(\n                """\n                SELECT\n                    ta.team_id,\n                    ta.area_id,\n                    ta.household_quota\n                FROM survey_team_area_assignments ta\n                JOIN survey_investigation_teams t\n                  ON t.id = ta.team_id\n                WHERE t.survey_batch_id = :batch_id\n                """\n            ),\n            {"batch_id": int(selected_batch["id"])},\n        ).mappings().all()\n\n        area_assigned = {}\n        for row in assignment_rows:\n            team_id_value = int(row["team_id"])\n            area_id_value = int(row["area_id"])\n            quota = max(0, _b1322_int(row["household_quota"]))\n            assignment_values[\n                f"{team_id_value}:{area_id_value}"\n            ] = quota\n            area_assigned[area_id_value] = (\n                area_assigned.get(area_id_value, 0) + quota\n            )\n\n        for area in areas:\n            area["assigned_quota_selected"] = area_assigned.get(\n                int(area["id"]),\n                0,\n            )\n\n    active_areas = [\n        item for item in areas if bool(item.get("is_active"))\n    ]\n\n    area_summary = {\n        "active_count": len(active_areas),\n        "expected_total": sum(\n            _b1322_int(a["expected_households"])\n            for a in active_areas\n        ),\n        "actual_total": sum(\n            _b1322_int(a["actual_households"])\n            for a in active_areas\n        ),\n    }\n    area_summary["remaining_total"] = max(\n        0,\n        area_summary["expected_total"]\n        - area_summary["actual_total"],\n    )\n\n    kind, message = _b1322_area_messages(status)\n\n    return templates.TemplateResponse(\n        request=request,\n        name="survey_teams/commune_areas_v2_2.html",\n        context={\n            "nguoi_dung": user,\n            "years": years,\n            "selected_year": selected_year,\n            "batches": batches,\n            "selected_batch": selected_batch,\n            "areas": areas,\n            "active_areas": active_areas,\n            "area_summary": area_summary,\n            "teams": teams,\n            "teams_locked": teams_locked,\n            "assignment_values": assignment_values,\n            "message": message,\n            "message_kind": kind,\n        },\n    )\n\n\n@router.post("/dia-ban/luu")\nasync def b1322_save_area(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n    _b1322_ensure_area_schema(db)\n\n    form = await request.form()\n    user = _user(request)\n    commune_id = _b1322_int(user.get("commune_id"))\n    school_year_id = _b1322_int(form.get("school_year_id"))\n    batch_id = _b1322_int(form.get("batch_id"))\n    area_id = _b1322_int(form.get("area_id"))\n    area_type = str(form.get("area_type") or "").strip().upper()\n    name = " ".join(\n        str(form.get("name") or "").strip().split()\n    )\n    expected = _b1322_int(form.get("expected_households"), -1)\n    notes = str(form.get("notes") or "").strip()[:500]\n\n    if (\n        not commune_id\n        or not school_year_id\n        or area_type not in _B1322_AREA_TYPES\n        or not name\n        or len(name) > 200\n        or expected < 0\n    ):\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="invalid",\n        )\n\n    actual_count = 0\n    if area_id:\n        existing = db.execute(\n            text(\n                """\n                SELECT id\n                FROM survey_commune_areas\n                WHERE id = :area_id\n                  AND commune_id = :commune_id\n                  AND school_year_id = :school_year_id\n                LIMIT 1\n                """\n            ),\n            {\n                "area_id": area_id,\n                "commune_id": commune_id,\n                "school_year_id": school_year_id,\n            },\n        ).scalar()\n        if existing is None:\n            return _b1322_redirect(\n                school_year_id=school_year_id,\n                batch_id=batch_id,\n                status="invalid",\n            )\n\n        locked_ref = db.execute(\n            text(\n                """\n                SELECT 1\n                FROM survey_team_area_assignments ta\n                JOIN survey_investigation_teams t\n                  ON t.id = ta.team_id\n                WHERE ta.area_id = :area_id\n                  AND t.status != \'DRAFT\'\n                LIMIT 1\n                """\n            ),\n            {"area_id": area_id},\n        ).scalar()\n        if locked_ref is not None:\n            return _b1322_redirect(\n                school_year_id=school_year_id,\n                batch_id=batch_id,\n                status="locked",\n            )\n\n        actual_count = _b1322_int(\n            db.execute(\n                text(\n                    """\n                    SELECT COUNT(*)\n                    FROM survey_form_areas\n                    WHERE area_id = :area_id\n                    """\n                ),\n                {"area_id": area_id},\n            ).scalar()\n        )\n        if expected < actual_count:\n            return _b1322_redirect(\n                school_year_id=school_year_id,\n                batch_id=batch_id,\n                status="invalid",\n            )\n\n    try:\n        now = _b1322_datetime.now()\n        if area_id:\n            db.execute(\n                text(\n                    """\n                    UPDATE survey_commune_areas\n                    SET name = :name,\n                        area_type = :area_type,\n                        expected_households = :expected,\n                        notes = :notes,\n                        updated_at = :updated_at\n                    WHERE id = :area_id\n                    """\n                ),\n                {\n                    "name": name,\n                    "area_type": area_type,\n                    "expected": expected,\n                    "notes": notes or None,\n                    "updated_at": now,\n                    "area_id": area_id,\n                },\n            )\n        else:\n            code = (\n                f"{area_type}-{commune_id}-{school_year_id}-"\n                f"{now.strftime(\'%Y%m%d%H%M%S%f\')}"\n            )\n            db.execute(\n                text(\n                    """\n                    INSERT INTO survey_commune_areas (\n                        commune_id,\n                        school_year_id,\n                        code,\n                        name,\n                        area_type,\n                        expected_households,\n                        notes,\n                        is_active,\n                        created_by_user_id,\n                        created_at,\n                        updated_at\n                    ) VALUES (\n                        :commune_id,\n                        :school_year_id,\n                        :code,\n                        :name,\n                        :area_type,\n                        :expected,\n                        :notes,\n                        1,\n                        :created_by_user_id,\n                        :created_at,\n                        :updated_at\n                    )\n                    """\n                ),\n                {\n                    "commune_id": commune_id,\n                    "school_year_id": school_year_id,\n                    "code": code,\n                    "name": name,\n                    "area_type": area_type,\n                    "expected": expected,\n                    "notes": notes or None,\n                    "created_by_user_id": user.get("id"),\n                    "created_at": now,\n                    "updated_at": now,\n                },\n            )\n        db.commit()\n    except Exception:\n        db.rollback()\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="duplicate",\n        )\n\n    return _b1322_redirect(\n        school_year_id=school_year_id,\n        batch_id=batch_id,\n        status="saved",\n    )\n\n\n@router.post("/dia-ban/ngung-dung")\nasync def b1322_deactivate_area(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n    _b1322_ensure_area_schema(db)\n    form = await request.form()\n    user = _user(request)\n    commune_id = _b1322_int(user.get("commune_id"))\n    area_id = _b1322_int(form.get("area_id"))\n    school_year_id = _b1322_int(form.get("school_year_id"))\n    batch_id = _b1322_int(form.get("batch_id"))\n\n    locked_ref = db.execute(\n        text(\n            """\n            SELECT 1\n            FROM survey_team_area_assignments ta\n            JOIN survey_investigation_teams t\n              ON t.id = ta.team_id\n            WHERE ta.area_id = :area_id\n              AND t.status != \'DRAFT\'\n            LIMIT 1\n            """\n        ),\n        {"area_id": area_id},\n    ).scalar()\n    form_ref = db.execute(\n        text(\n            """\n            SELECT 1 FROM survey_form_areas\n            WHERE area_id = :area_id\n            LIMIT 1\n            """\n        ),\n        {"area_id": area_id},\n    ).scalar()\n\n    if locked_ref is not None or form_ref is not None:\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="locked",\n        )\n\n    db.execute(\n        text(\n            """\n            DELETE FROM survey_team_area_assignments\n            WHERE area_id = :area_id\n            """\n        ),\n        {"area_id": area_id},\n    )\n    db.execute(\n        text(\n            """\n            UPDATE survey_commune_areas\n            SET is_active = 0,\n                updated_at = :updated_at\n            WHERE id = :area_id\n              AND commune_id = :commune_id\n            """\n        ),\n        {\n            "updated_at": _b1322_datetime.now(),\n            "area_id": area_id,\n            "commune_id": commune_id,\n        },\n    )\n    db.commit()\n    return _b1322_redirect(\n        school_year_id=school_year_id,\n        batch_id=batch_id,\n        status="deactivated",\n    )\n\n\n@router.post("/dia-ban/kich-hoat")\nasync def b1322_activate_area(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n    _b1322_ensure_area_schema(db)\n    form = await request.form()\n    user = _user(request)\n    area_id = _b1322_int(form.get("area_id"))\n    school_year_id = _b1322_int(form.get("school_year_id"))\n    batch_id = _b1322_int(form.get("batch_id"))\n\n    db.execute(\n        text(\n            """\n            UPDATE survey_commune_areas\n            SET is_active = 1,\n                updated_at = :updated_at\n            WHERE id = :area_id\n              AND commune_id = :commune_id\n            """\n        ),\n        {\n            "updated_at": _b1322_datetime.now(),\n            "area_id": area_id,\n            "commune_id": _b1322_int(user.get("commune_id")),\n        },\n    )\n    db.commit()\n    return _b1322_redirect(\n        school_year_id=school_year_id,\n        batch_id=batch_id,\n        status="activated",\n    )\n\n\ndef _b1322_batch_teams_and_areas(db, request, batch_id):\n    batch = _commune_batch_scope(db, request, int(batch_id))\n    if batch is None:\n        return None, [], []\n\n    teams = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT id, team_number, status\n                FROM survey_investigation_teams\n                WHERE survey_batch_id = :batch_id\n                ORDER BY team_number\n                """\n            ),\n            {"batch_id": int(batch_id)},\n        ).mappings().all()\n    ]\n\n    areas = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT id, name, area_type, expected_households\n                FROM survey_commune_areas\n                WHERE commune_id = :commune_id\n                  AND school_year_id = :school_year_id\n                  AND is_active = 1\n                  AND expected_households > 0\n                ORDER BY name COLLATE NOCASE, id\n                """\n            ),\n            {\n                "commune_id": int(batch["commune_id"]),\n                "school_year_id": int(batch["school_year_id"]),\n            },\n        ).mappings().all()\n    ]\n    return batch, teams, areas\n\n\n@router.post("/dia-ban/phan-cong-luu")\nasync def b1322_save_area_assignments(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n    _b1322_ensure_area_schema(db)\n\n    form = await request.form()\n    batch_id = _b1322_int(form.get("batch_id"))\n    school_year_id = _b1322_int(form.get("school_year_id"))\n    batch, teams, areas = _b1322_batch_teams_and_areas(\n        db, request, batch_id\n    )\n\n    if batch is None or not teams:\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="no_teams",\n        )\n\n    if any(str(t["status"]) != "DRAFT" for t in teams):\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="team_locked",\n        )\n\n    team_ids = {int(t["id"]) for t in teams}\n    area_ids = {int(a["id"]) for a in areas}\n    values = {}\n    area_totals = {area_id: 0 for area_id in area_ids}\n\n    for key, raw in form.multi_items():\n        if not str(key).startswith("quota__"):\n            continue\n        parts = str(key).split("__")\n        if len(parts) != 3:\n            continue\n        team_id = _b1322_int(parts[1])\n        area_id = _b1322_int(parts[2])\n        quota = _b1322_int(raw, -1)\n        if (\n            team_id not in team_ids\n            or area_id not in area_ids\n            or quota < 0\n        ):\n            return _b1322_redirect(\n                school_year_id=school_year_id,\n                batch_id=batch_id,\n                status="invalid",\n            )\n        if quota:\n            values[(team_id, area_id)] = quota\n            area_totals[area_id] += quota\n\n    expected_map = {\n        int(a["id"]): int(a["expected_households"] or 0)\n        for a in areas\n    }\n    if any(\n        area_totals.get(area_id, 0) > expected\n        for area_id, expected in expected_map.items()\n    ):\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="over_expected",\n        )\n\n    now = _b1322_datetime.now()\n    try:\n        db.execute(\n            text(\n                """\n                DELETE FROM survey_team_area_assignments\n                WHERE team_id IN (\n                    SELECT id\n                    FROM survey_investigation_teams\n                    WHERE survey_batch_id = :batch_id\n                )\n                """\n            ),\n            {"batch_id": batch_id},\n        )\n        user_id = _user(request).get("id")\n        for (team_id, area_id), quota in values.items():\n            db.execute(\n                text(\n                    """\n                    INSERT INTO survey_team_area_assignments (\n                        team_id,\n                        area_id,\n                        household_quota,\n                        created_by_user_id,\n                        created_at,\n                        updated_at\n                    ) VALUES (\n                        :team_id,\n                        :area_id,\n                        :household_quota,\n                        :created_by_user_id,\n                        :created_at,\n                        :updated_at\n                    )\n                    """\n                ),\n                {\n                    "team_id": team_id,\n                    "area_id": area_id,\n                    "household_quota": quota,\n                    "created_by_user_id": user_id,\n                    "created_at": now,\n                    "updated_at": now,\n                },\n            )\n        db.commit()\n    except Exception:\n        db.rollback()\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="invalid",\n        )\n\n    return _b1322_redirect(\n        school_year_id=school_year_id,\n        batch_id=batch_id,\n        status="assign_saved",\n    )\n\n\n@router.post("/dia-ban/chia-deu")\nasync def b1322_auto_distribute_areas(\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != COMMUNE_ROLE_CODE:\n        return _forbidden()\n    _b1322_ensure_area_schema(db)\n\n    form = await request.form()\n    batch_id = _b1322_int(form.get("batch_id"))\n    school_year_id = _b1322_int(form.get("school_year_id"))\n    batch, teams, areas = _b1322_batch_teams_and_areas(\n        db, request, batch_id\n    )\n\n    if batch is None or not teams:\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="no_teams",\n        )\n    if not areas:\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="no_areas",\n        )\n    if any(str(t["status"]) != "DRAFT" for t in teams):\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="team_locked",\n        )\n\n    total = sum(\n        int(a["expected_households"] or 0) for a in areas\n    )\n    team_count = len(teams)\n    base = total // team_count\n    extra = total % team_count\n    capacities = {\n        int(team["id"]): base + (\n            1 if index < extra else 0\n        )\n        for index, team in enumerate(teams)\n    }\n\n    allocations = {}\n    team_index = 0\n    ordered_team_ids = [int(t["id"]) for t in teams]\n\n    for area in areas:\n        remaining = int(area["expected_households"] or 0)\n        area_id = int(area["id"])\n        while remaining > 0 and team_index < len(ordered_team_ids):\n            team_id = ordered_team_ids[team_index]\n            capacity = capacities.get(team_id, 0)\n            if capacity <= 0:\n                team_index += 1\n                continue\n            amount = min(remaining, capacity)\n            allocations[(team_id, area_id)] = (\n                allocations.get((team_id, area_id), 0)\n                + amount\n            )\n            capacities[team_id] -= amount\n            remaining -= amount\n            if capacities[team_id] <= 0:\n                team_index += 1\n\n    now = _b1322_datetime.now()\n    try:\n        db.execute(\n            text(\n                """\n                DELETE FROM survey_team_area_assignments\n                WHERE team_id IN (\n                    SELECT id\n                    FROM survey_investigation_teams\n                    WHERE survey_batch_id = :batch_id\n                )\n                """\n            ),\n            {"batch_id": batch_id},\n        )\n        user_id = _user(request).get("id")\n        for (team_id, area_id), quota in allocations.items():\n            if quota <= 0:\n                continue\n            db.execute(\n                text(\n                    """\n                    INSERT INTO survey_team_area_assignments (\n                        team_id, area_id, household_quota,\n                        created_by_user_id, created_at, updated_at\n                    ) VALUES (\n                        :team_id, :area_id, :quota,\n                        :user_id, :created_at, :updated_at\n                    )\n                    """\n                ),\n                {\n                    "team_id": team_id,\n                    "area_id": area_id,\n                    "quota": quota,\n                    "user_id": user_id,\n                    "created_at": now,\n                    "updated_at": now,\n                },\n            )\n        db.commit()\n    except Exception:\n        db.rollback()\n        return _b1322_redirect(\n            school_year_id=school_year_id,\n            batch_id=batch_id,\n            status="invalid",\n        )\n\n    return _b1322_redirect(\n        school_year_id=school_year_id,\n        batch_id=batch_id,\n        status="distributed",\n    )\n# ============================================================\n# BAI_13B_12_V2_2_AREA_WORKFLOW_END\n# ============================================================\n'
TEAM_NEW_HOUSE_BLOCK = '\n# ============================================================\n# BAI_13B_12_V2_2_TEAM_NEW_HOUSEHOLD_START\n# Tổ đã chốt/gửi trực tiếp tạo hộ thực tế tại địa bàn được giao.\n# URL nằm trong router tổ điều tra để không xung đột route household_id.\n# ============================================================\nfrom uuid import uuid4 as _b1322_uuid4\nfrom fastapi.responses import JSONResponse as _b1322_JSONResponse\n\n\ndef _b1322_team_context_for_teacher(\n    db: Session,\n    *,\n    batch_id: int,\n    user_id: int,\n):\n    batch = db.execute(\n        text(\n            """\n            SELECT\n                sb.id,\n                sb.code,\n                sb.name,\n                sb.status,\n                sb.is_locked,\n                sb.commune_id,\n                sb.school_year_id,\n                sy.code AS school_year_code\n            FROM survey_batches sb\n            JOIN school_years sy\n              ON sy.id = sb.school_year_id\n            WHERE sb.id = :batch_id\n            LIMIT 1\n            """\n        ),\n        {"batch_id": int(batch_id)},\n    ).mappings().first()\n\n    if batch is None:\n        return None, None, [], []\n\n    team = db.execute(\n        text(\n            """\n            SELECT\n                t.id,\n                t.team_number,\n                t.status,\n                t.commune_id,\n                t.survey_batch_id\n            FROM survey_investigation_teams t\n            JOIN survey_investigation_team_members tm\n              ON tm.team_id = t.id\n            WHERE t.survey_batch_id = :batch_id\n              AND tm.user_id = :user_id\n              AND t.status = \'SENT\'\n            ORDER BY t.team_number\n            LIMIT 1\n            """\n        ),\n        {\n            "batch_id": int(batch_id),\n            "user_id": int(user_id),\n        },\n    ).mappings().first()\n\n    if team is None:\n        return dict(batch), None, [], []\n\n    members = [\n        dict(row)\n        for row in db.execute(\n            text(\n                """\n                SELECT\n                    tm.user_id,\n                    tm.level_code,\n                    tm.order_number,\n                    u.full_name,\n                    COALESCE(s.name, \'\') AS school_name\n                FROM survey_investigation_team_members tm\n                JOIN users u ON u.id = tm.user_id\n                LEFT JOIN schools s ON s.id = tm.school_id\n                WHERE tm.team_id = :team_id\n                  AND u.is_active = 1\n                ORDER BY tm.order_number\n                """\n            ),\n            {"team_id": int(team["id"])},\n        ).mappings().all()\n    ]\n\n    labels = {\n        "THON": "Thôn",\n        "XOM": "Xóm",\n        "KHOI": "Khối",\n        "TO": "Tổ",\n        "BAN": "Bản",\n    }\n\n    assignment_rows = db.execute(\n        text(\n            """\n            SELECT\n                ta.area_id,\n                ta.household_quota,\n                a.name AS area_name,\n                a.area_type,\n                COALESCE(\n                    (\n                        SELECT COUNT(*)\n                        FROM survey_investigation_team_forms tf\n                        JOIN survey_form_areas fa\n                          ON fa.survey_form_id = tf.survey_form_id\n                        WHERE tf.team_id = ta.team_id\n                          AND fa.area_id = ta.area_id\n                    ),\n                    0\n                ) AS actual_count\n            FROM survey_team_area_assignments ta\n            JOIN survey_commune_areas a\n              ON a.id = ta.area_id\n            WHERE ta.team_id = :team_id\n              AND a.is_active = 1\n              AND ta.household_quota > 0\n            ORDER BY a.name COLLATE NOCASE, a.id\n            """\n        ),\n        {"team_id": int(team["id"])},\n    ).mappings().all()\n\n    assignments = []\n    for row in assignment_rows:\n        item = dict(row)\n        item["area_type_label"] = labels.get(\n            str(item.get("area_type") or ""),\n            str(item.get("area_type") or ""),\n        )\n        item["remaining_count"] = max(\n            0,\n            int(item["household_quota"] or 0)\n            - int(item["actual_count"] or 0),\n        )\n        if item["remaining_count"] > 0:\n            assignments.append(item)\n\n    return dict(batch), dict(team), members, assignments\n\n\n@router.get("/nhap-ho-moi/{batch_id}/quyen")\ndef b1322_teacher_new_house_permission(\n    batch_id: int,\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != TEACHER_ROLE_CODE:\n        return _b1322_JSONResponse({"can_create": False})\n\n    _b1322_ensure_area_schema(db)\n    user = _user(request)\n    user_id = _b1322_int(user.get("id"))\n    if not user_id:\n        return _b1322_JSONResponse({"can_create": False})\n\n    batch, team, members, assignments = (\n        _b1322_team_context_for_teacher(\n            db,\n            batch_id=int(batch_id),\n            user_id=user_id,\n        )\n    )\n\n    can_create = bool(\n        batch\n        and not bool(batch.get("is_locked"))\n        and str(batch.get("status") or "") != "DA_KET_THUC"\n        and team\n        and len(members) == 3\n        and assignments\n    )\n\n    return _b1322_JSONResponse(\n        {\n            "can_create": can_create,\n            "team_number": (\n                int(team["team_number"]) if team else None\n            ),\n            "remaining_quota": sum(\n                int(item["remaining_count"])\n                for item in assignments\n            ),\n        }\n    )\n\n\n@router.get(\n    "/nhap-ho-moi/{batch_id}",\n    response_class=HTMLResponse,\n)\ndef b1322_teacher_new_house_page(\n    batch_id: int,\n    request: Request,\n    status: str | None = None,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != TEACHER_ROLE_CODE:\n        return _forbidden()\n\n    _b1322_ensure_area_schema(db)\n    user = _user(request)\n    user_id = _b1322_int(user.get("id"))\n    batch, team, members, assignments = (\n        _b1322_team_context_for_teacher(\n            db,\n            batch_id=int(batch_id),\n            user_id=user_id,\n        )\n    )\n\n    if (\n        not batch\n        or bool(batch.get("is_locked"))\n        or str(batch.get("status") or "") == "DA_KET_THUC"\n        or team is None\n        or len(members) != 3\n    ):\n        return RedirectResponse(\n            url=f"/dieu-tra/{batch_id}/ho-dan",\n            status_code=303,\n        )\n\n    # Dùng dict lồng nhau để template vẫn truy cập batch.school_year.code.\n    batch_view = dict(batch)\n    batch_view["school_year"] = {\n        "code": batch_view.get("school_year_code")\n    }\n\n    messages = {\n        "invalid": "Thông tin hộ hoặc địa bàn chưa hợp lệ.",\n        "quota_full": "Địa bàn đã đủ chỉ tiêu hộ của tổ; không thể tạo thêm hộ.",\n        "save_error": "Không lưu được hộ mới. Dữ liệu đã được rollback.",\n    }\n\n    return templates.TemplateResponse(\n        request=request,\n        name="surveys/new_household_team_v2_2.html",\n        context={\n            "nguoi_dung": user,\n            "batch": batch_view,\n            "team": team,\n            "members": members,\n            "assignments": assignments,\n            "message": messages.get(str(status or "")),\n        },\n    )\n\n\n@router.post("/nhap-ho-moi/{batch_id}/them")\nasync def b1322_teacher_create_new_house(\n    batch_id: int,\n    request: Request,\n    db: Session = Depends(get_db),\n):\n    if _role(request) != TEACHER_ROLE_CODE:\n        return _forbidden()\n\n    _b1322_ensure_area_schema(db)\n    user = _user(request)\n    user_id = _b1322_int(user.get("id"))\n\n    batch, team, members, assignments = (\n        _b1322_team_context_for_teacher(\n            db,\n            batch_id=int(batch_id),\n            user_id=user_id,\n        )\n    )\n\n    if (\n        not batch\n        or bool(batch.get("is_locked"))\n        or str(batch.get("status") or "") == "DA_KET_THUC"\n        or team is None\n        or len(members) != 3\n    ):\n        return RedirectResponse(\n            url=f"/dieu-tra/{batch_id}/ho-dan",\n            status_code=303,\n        )\n\n    form = await request.form()\n    area_id = _b1322_int(form.get("area_id"))\n    head_name = " ".join(\n        str(form.get("head_name") or "").strip().split()\n    )\n    address = " ".join(\n        str(form.get("address") or "").strip().split()\n    )\n    phone = " ".join(\n        str(form.get("phone") or "").strip().split()\n    )\n    notes = str(form.get("notes") or "").strip()\n\n    if (\n        not area_id\n        or not head_name\n        or len(head_name) > 200\n        or not address\n        or len(phone) > 30\n    ):\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/"\n                f"nhap-ho-moi/{batch_id}?status=invalid"\n            ),\n            status_code=303,\n        )\n\n    assignment = next(\n        (\n            item for item in assignments\n            if int(item["area_id"]) == int(area_id)\n        ),\n        None,\n    )\n    if assignment is None:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/"\n                f"nhap-ho-moi/{batch_id}?status=quota_full"\n            ),\n            status_code=303,\n        )\n\n    quota = int(assignment["household_quota"] or 0)\n    actual_before = int(\n        db.execute(\n            text(\n                """\n                SELECT COUNT(*)\n                FROM survey_investigation_team_forms tf\n                JOIN survey_form_areas fa\n                  ON fa.survey_form_id = tf.survey_form_id\n                WHERE tf.team_id = :team_id\n                  AND fa.area_id = :area_id\n                """\n            ),\n            {\n                "team_id": int(team["id"]),\n                "area_id": int(area_id),\n            },\n        ).scalar()\n        or 0\n    )\n    if actual_before >= quota:\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/"\n                f"nhap-ho-moi/{batch_id}?status=quota_full"\n            ),\n            status_code=303,\n        )\n\n    now = _b1322_datetime.now()\n    temp_house = (\n        "TMP-HO-" + _b1322_uuid4().hex[:20].upper()\n    )\n    temp_form = (\n        "TMP-PH-" + _b1322_uuid4().hex[:20].upper()\n    )\n\n    try:\n        cursor = db.execute(\n            text(\n                """\n                INSERT INTO households (\n                    code,\n                    commune_id,\n                    head_name,\n                    hamlet_name,\n                    address,\n                    phone,\n                    notes,\n                    is_active,\n                    created_at,\n                    updated_at\n                ) VALUES (\n                    :code,\n                    :commune_id,\n                    :head_name,\n                    :hamlet_name,\n                    :address,\n                    :phone,\n                    :notes,\n                    1,\n                    :created_at,\n                    :updated_at\n                )\n                """\n            ),\n            {\n                "code": temp_house,\n                "commune_id": int(batch["commune_id"]),\n                "head_name": head_name,\n                "hamlet_name": str(assignment["area_name"]),\n                "address": address,\n                "phone": phone or None,\n                "notes": notes or None,\n                "created_at": now,\n                "updated_at": now,\n            },\n        )\n        household_id = int(cursor.lastrowid)\n\n        household_code = (\n            f"HO-{int(batch[\'commune_id\']):05d}-"\n            f"{household_id:08d}"\n        )\n        db.execute(\n            text(\n                """\n                UPDATE households\n                SET code = :code\n                WHERE id = :household_id\n                """\n            ),\n            {\n                "code": household_code,\n                "household_id": household_id,\n            },\n        )\n\n        cursor = db.execute(\n            text(\n                """\n                INSERT INTO survey_forms (\n                    survey_batch_id,\n                    household_id,\n                    form_number,\n                    head_name_snapshot,\n                    address_snapshot,\n                    hamlet_name_snapshot,\n                    survey_date,\n                    status,\n                    village_head_name,\n                    household_representative_name,\n                    household_confirmed_at,\n                    commune_confirmed_at,\n                    notes,\n                    created_at,\n                    updated_at\n                ) VALUES (\n                    :survey_batch_id,\n                    :household_id,\n                    :form_number,\n                    :head_name,\n                    :address,\n                    :hamlet_name,\n                    NULL,\n                    \'CHUA_DIEU_TRA\',\n                    NULL,\n                    NULL,\n                    NULL,\n                    NULL,\n                    :notes,\n                    :created_at,\n                    :updated_at\n                )\n                """\n            ),\n            {\n                "survey_batch_id": int(batch_id),\n                "household_id": household_id,\n                "form_number": temp_form,\n                "head_name": head_name,\n                "address": address,\n                "hamlet_name": str(assignment["area_name"]),\n                "notes": (\n                    "[V2.2] Hộ được tổ điều tra tạo mới "\n                    "trực tiếp tại thực địa."\n                ),\n                "created_at": now,\n                "updated_at": now,\n            },\n        )\n        survey_form_id = int(cursor.lastrowid)\n\n        form_number = (\n            f"PH-{int(batch_id):06d}-"\n            f"{survey_form_id:08d}"\n        )\n        db.execute(\n            text(\n                """\n                UPDATE survey_forms\n                SET form_number = :form_number\n                WHERE id = :survey_form_id\n                """\n            ),\n            {\n                "form_number": form_number,\n                "survey_form_id": survey_form_id,\n            },\n        )\n\n        db.execute(\n            text(\n                """\n                INSERT INTO survey_form_areas (\n                    survey_form_id,\n                    area_id,\n                    created_at\n                ) VALUES (\n                    :survey_form_id,\n                    :area_id,\n                    :created_at\n                )\n                """\n            ),\n            {\n                "survey_form_id": survey_form_id,\n                "area_id": int(area_id),\n                "created_at": now,\n            },\n        )\n\n        next_order = int(\n            db.execute(\n                text(\n                    """\n                    SELECT COALESCE(MAX(assignment_order), 0) + 1\n                    FROM survey_investigation_team_forms\n                    WHERE team_id = :team_id\n                    """\n                ),\n                {"team_id": int(team["id"])},\n            ).scalar()\n            or 1\n        )\n\n        db.execute(\n            text(\n                """\n                INSERT INTO survey_investigation_team_forms (\n                    team_id,\n                    survey_form_id,\n                    assignment_order,\n                    created_at\n                ) VALUES (\n                    :team_id,\n                    :survey_form_id,\n                    :assignment_order,\n                    :created_at\n                )\n                """\n            ),\n            {\n                "team_id": int(team["id"]),\n                "survey_form_id": survey_form_id,\n                "assignment_order": next_order,\n                "created_at": now,\n            },\n        )\n\n        for member in members:\n            order_number = int(member["order_number"])\n            db.execute(\n                text(\n                    """\n                    INSERT INTO survey_form_investigators (\n                        survey_form_id,\n                        user_id,\n                        order_number,\n                        is_primary,\n                        signed_at,\n                        notes,\n                        created_at\n                    ) VALUES (\n                        :survey_form_id,\n                        :user_id,\n                        :order_number,\n                        :is_primary,\n                        :signed_at,\n                        :notes,\n                        :created_at\n                    )\n                    """\n                ),\n                {\n                    "survey_form_id": survey_form_id,\n                    "user_id": int(member["user_id"]),\n                    "order_number": order_number,\n                    "is_primary": 1 if order_number == 1 else 0,\n                    "signed_at": now,\n                    "notes": (\n                        f"Tổ điều tra 3 cấp số "\n                        f"{int(team[\'team_number\'])}; "\n                        f"{member[\'level_code\']}; "\n                        "hộ tạo mới tại thực địa."\n                    ),\n                    "created_at": now,\n                },\n            )\n\n        actual_after = int(\n            db.execute(\n                text(\n                    """\n                    SELECT COUNT(*)\n                    FROM survey_investigation_team_forms tf\n                    JOIN survey_form_areas fa\n                      ON fa.survey_form_id = tf.survey_form_id\n                    WHERE tf.team_id = :team_id\n                      AND fa.area_id = :area_id\n                    """\n                ),\n                {\n                    "team_id": int(team["id"]),\n                    "area_id": int(area_id),\n                },\n            ).scalar()\n            or 0\n        )\n        if actual_after > quota:\n            raise RuntimeError(\n                "Vượt chỉ tiêu hộ của tổ tại địa bàn."\n            )\n\n        db.commit()\n\n    except Exception:\n        db.rollback()\n        return RedirectResponse(\n            url=(\n                "/dieu-tra/phan-cong-to-dieu-tra/"\n                f"nhap-ho-moi/{batch_id}?status=save_error"\n            ),\n            status_code=303,\n        )\n\n    return RedirectResponse(\n        url=(\n            f"/dieu-tra/{batch_id}/ho-dan/"\n            f"{household_id}/nhap-nhanh"\n            "?status=household_created"\n        ),\n        status_code=303,\n    )\n# ============================================================\n# BAI_13B_12_V2_2_TEAM_NEW_HOUSEHOLD_END\n# ============================================================\n'
SCHEMA_SQL = ('CREATE TABLE IF NOT EXISTS survey_commune_areas (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    commune_id INTEGER NOT NULL,\n    school_year_id INTEGER NOT NULL,\n    code VARCHAR(80) NOT NULL,\n    name VARCHAR(200) NOT NULL,\n    area_type VARCHAR(20) NOT NULL,\n    expected_households INTEGER NOT NULL DEFAULT 0,\n    notes TEXT NULL,\n    is_active BOOLEAN NOT NULL DEFAULT 1,\n    created_by_user_id INTEGER NULL,\n    created_at DATETIME NOT NULL,\n    updated_at DATETIME NOT NULL,\n    UNIQUE(commune_id, school_year_id, code),\n    FOREIGN KEY(commune_id) REFERENCES communes(id),\n    FOREIGN KEY(school_year_id) REFERENCES school_years(id),\n    FOREIGN KEY(created_by_user_id) REFERENCES users(id)\n)', 'CREATE UNIQUE INDEX IF NOT EXISTS uq_survey_commune_areas_name\nON survey_commune_areas(\n    commune_id, school_year_id, area_type, name COLLATE NOCASE\n)', 'CREATE TABLE IF NOT EXISTS survey_team_area_assignments (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    team_id INTEGER NOT NULL,\n    area_id INTEGER NOT NULL,\n    household_quota INTEGER NOT NULL DEFAULT 0,\n    notes TEXT NULL,\n    created_by_user_id INTEGER NULL,\n    created_at DATETIME NOT NULL,\n    updated_at DATETIME NOT NULL,\n    UNIQUE(team_id, area_id),\n    FOREIGN KEY(team_id) REFERENCES survey_investigation_teams(id) ON DELETE CASCADE,\n    FOREIGN KEY(area_id) REFERENCES survey_commune_areas(id),\n    FOREIGN KEY(created_by_user_id) REFERENCES users(id)\n)', 'CREATE INDEX IF NOT EXISTS ix_survey_team_area_assignments_area\nON survey_team_area_assignments(area_id)', 'CREATE TABLE IF NOT EXISTS survey_form_areas (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    survey_form_id INTEGER NOT NULL UNIQUE,\n    area_id INTEGER NOT NULL,\n    created_at DATETIME NOT NULL,\n    FOREIGN KEY(survey_form_id) REFERENCES survey_forms(id),\n    FOREIGN KEY(area_id) REFERENCES survey_commune_areas(id)\n)', 'CREATE INDEX IF NOT EXISTS ix_survey_form_areas_area\nON survey_form_areas(area_id)')
OLD_SURVEY_TEACHER_FILTER = '    if role_code == "GIAO_VIEN":\n        user_id = user.get("id")\n        if user_id is None:\n            return [SurveyBatch.id == -1]\n\n        return [\n            SurveyBatch.survey_forms.any(\n                SurveyForm.investigators.any(\n                    SurveyFormInvestigator.user_id == int(user_id)\n                )\n            )\n        ]\n'
NEW_SURVEY_TEACHER_FILTER = '    # === BAI_13B_12_V2_2_TEACHER_BATCH_SCOPE_START ===\n    if role_code == "GIAO_VIEN":\n        user_id = user.get("id")\n        if user_id is None:\n            return [SurveyBatch.id == -1]\n\n        legacy_assigned_form = (\n            SurveyBatch.survey_forms.any(\n                SurveyForm.investigators.any(\n                    SurveyFormInvestigator.user_id == int(user_id)\n                )\n            )\n        )\n        team_membership = text(\n            "EXISTS ("\n            "SELECT 1 "\n            "FROM survey_investigation_teams AS b1322_t "\n            "JOIN survey_investigation_team_members AS b1322_tm "\n            "ON b1322_tm.team_id = b1322_t.id "\n            "WHERE b1322_t.survey_batch_id = survey_batches.id "\n            "AND b1322_t.status = \'SENT\' "\n            f"AND b1322_tm.user_id = {int(user_id)}"\n            ")"\n        )\n\n        return [\n            or_(\n                legacy_assigned_form,\n                team_membership,\n            )\n        ]\n    # === BAI_13B_12_V2_2_TEACHER_BATCH_SCOPE_END ===\n'
ACCESS_BATCH_EXTRA = '        if allowed is not None:\n            return True\n\n        # === BAI_13B_12_V2_2_ACCESS_BATCH_SCOPE ===\n        team_allowed = db.execute(\n            text(\n                """\n                SELECT 1\n                FROM survey_investigation_teams AS t\n                JOIN survey_investigation_team_members AS tm\n                  ON tm.team_id = t.id\n                WHERE t.survey_batch_id = :batch_id\n                  AND t.status = \'SENT\'\n                  AND tm.user_id = :user_id\n                LIMIT 1\n                """\n            ),\n            {\n                "batch_id": int(batch_id),\n                "user_id": int(user_id),\n            },\n        ).scalar()\n        return team_allowed is not None'
OLD_ACCESS_LATEST_SQL = '                SELECT DISTINCT sb.id\n                FROM survey_batches AS sb\n                JOIN survey_forms AS sf\n                    ON sf.survey_batch_id = sb.id\n                JOIN survey_form_investigators AS sfi\n                    ON sfi.survey_form_id = sf.id\n                WHERE sfi.user_id = :user_id\n                ORDER BY\n                    sb.school_year_id DESC,\n                    sb.created_at DESC,\n                    sb.id DESC\n                LIMIT 1\n'
NEW_ACCESS_LATEST_SQL = "                -- === BAI_13B_12_V2_2_ACCESS_LATEST_BATCH ===\n                SELECT sb.id\n                FROM survey_batches AS sb\n                WHERE\n                    EXISTS (\n                        SELECT 1\n                        FROM survey_forms AS sf\n                        JOIN survey_form_investigators AS sfi\n                          ON sfi.survey_form_id = sf.id\n                        WHERE sf.survey_batch_id = sb.id\n                          AND sfi.user_id = :user_id\n                    )\n                    OR EXISTS (\n                        SELECT 1\n                        FROM survey_investigation_teams AS t\n                        JOIN survey_investigation_team_members AS tm\n                          ON tm.team_id = t.id\n                        WHERE t.survey_batch_id = sb.id\n                          AND t.status = 'SENT'\n                          AND tm.user_id = :user_id\n                    )\n                ORDER BY\n                    sb.school_year_id DESC,\n                    sb.created_at DESC,\n                    sb.id DESC\n                LIMIT 1\n"
ACCESS_ACTION_BLOCK = '        # === BAI_13B_12_V2_2_ACCESS_ACTION_START ===\n        if normalized_path.startswith(\n            "/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/"\n        ):\n            return role_code == TEACHER_ROLE_CODE\n        # === BAI_13B_12_V2_2_ACCESS_ACTION_END ===\n\n'
ACCESS_SCOPE_BLOCK = '        # === BAI_13B_12_V2_2_ACCESS_SCOPE_START ===\n        if normalized_path.startswith(\n            "/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/"\n        ):\n            if role_code != TEACHER_ROLE_CODE:\n                return False\n            user_id = auth_user.get("id")\n            if user_id is None:\n                return False\n            allowed = db.execute(\n                text(\n                    """\n                    SELECT 1\n                    FROM survey_investigation_teams AS t\n                    JOIN survey_investigation_team_members AS tm\n                      ON tm.team_id = t.id\n                    WHERE t.survey_batch_id = :batch_id\n                      AND t.status = \'SENT\'\n                      AND tm.user_id = :user_id\n                    LIMIT 1\n                    """\n                ),\n                {\n                    "batch_id": int(batch_id),\n                    "user_id": int(user_id),\n                },\n            ).scalar()\n            return allowed is not None\n        # === BAI_13B_12_V2_2_ACCESS_SCOPE_END ===\n\n'
OLD_FINALIZE_NO_FORMS = '            if not form_ids:\n                raise RuntimeError(\n                    f"Tổ {team_number} không có hộ/phiếu."\n                )\n'
NEW_FINALIZE_NO_FORMS = '            # === BAI_13B_12_V2_2_FINALIZE_WITH_AREA_START ===\n            if not form_ids:\n                quota_total = int(\n                    db.execute(\n                        text(\n                            """\n                            SELECT COALESCE(SUM(household_quota), 0)\n                            FROM survey_team_area_assignments\n                            WHERE team_id = :team_id\n                            """\n                        ),\n                        {"team_id": team_id},\n                    ).scalar()\n                    or 0\n                )\n\n                if quota_total <= 0:\n                    raise RuntimeError(\n                        f"Tổ {team_number} chưa được giao địa bàn/chỉ tiêu hộ."\n                    )\n\n                invalid_area = db.execute(\n                    text(\n                        """\n                        SELECT\n                            a.name,\n                            a.expected_households,\n                            COALESCE(\n                                (\n                                    SELECT SUM(ta.household_quota)\n                                    FROM survey_team_area_assignments ta\n                                    JOIN survey_investigation_teams it\n                                      ON it.id = ta.team_id\n                                    WHERE ta.area_id = a.id\n                                      AND it.survey_batch_id = :batch_id\n                                ),\n                                0\n                            ) AS assigned_total\n                        FROM survey_commune_areas a\n                        JOIN survey_batches sb\n                          ON sb.commune_id = a.commune_id\n                         AND sb.school_year_id = a.school_year_id\n                        WHERE sb.id = :batch_id\n                          AND a.is_active = 1\n                          AND a.expected_households > 0\n                          AND COALESCE(\n                                (\n                                    SELECT SUM(ta2.household_quota)\n                                    FROM survey_team_area_assignments ta2\n                                    JOIN survey_investigation_teams it2\n                                      ON it2.id = ta2.team_id\n                                    WHERE ta2.area_id = a.id\n                                      AND it2.survey_batch_id = :batch_id\n                                ),\n                                0\n                              ) != a.expected_households\n                        LIMIT 1\n                        """\n                    ),\n                    {"batch_id": int(batch_id)},\n                ).mappings().first()\n\n                if invalid_area is not None:\n                    raise RuntimeError(\n                        "Địa bàn "\n                        f"{invalid_area[\'name\']} chưa được giao đủ chỉ tiêu "\n                        f"({invalid_area[\'assigned_total\']}/"\n                        f"{invalid_area[\'expected_households\']})."\n                    )\n\n                # V2.2: chốt/gửi tổ trước; phiếu được tạo khi đi thực địa.\n                continue\n            # === BAI_13B_12_V2_2_FINALIZE_WITH_AREA_END ===\n'
MOBILE_BUTTON = '\n        <!-- === BAI_13B_12_V2_2_NEW_HOUSE_BUTTON_MOBILE_START === -->\n        <a\n            class="button button-primary b1322-new-household-link"\n            href="/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/{{ batch.id }}"\n            hidden\n            style="display:none;margin:0 0 12px;width:100%;justify-content:center;"\n        >\n            ➕ Điều tra mới – Nhập hộ dân mới\n        </a>\n        <!-- === BAI_13B_12_V2_2_NEW_HOUSE_BUTTON_MOBILE_END === -->\n'
DESKTOP_BUTTON = '            <!-- === BAI_13B_12_V2_2_NEW_HOUSE_BUTTON_DESKTOP_START === -->\n            {% if nguoi_dung.role_code == \'GIAO_VIEN\' and not batch.is_locked %}\n                <a\n                    class="button button-primary b1322-new-household-link"\n                    href="/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/{{ batch.id }}"\n                    hidden\n                    style="display:none"\n                >\n                    ➕ Điều tra mới – Nhập hộ dân mới\n                </a>\n            {% endif %}\n            <!-- === BAI_13B_12_V2_2_NEW_HOUSE_BUTTON_DESKTOP_END === -->\n\n'
HOUSE_BUTTON_JS = '<!-- === BAI_13B_12_V2_2_NEW_HOUSE_BUTTON_JS_START === -->\n<script>\n(function () {\n    "use strict";\n    {% if nguoi_dung.role_code == \'GIAO_VIEN\' and not batch.is_locked %}\n    fetch(\n        "/dieu-tra/phan-cong-to-dieu-tra/nhap-ho-moi/{{ batch.id }}/quyen",\n        {credentials: "same-origin"}\n    )\n    .then(function (response) {\n        if (!response.ok) return null;\n        return response.json();\n    })\n    .then(function (data) {\n        if (!data || !data.can_create) return;\n        document.querySelectorAll(\n            ".b1322-new-household-link"\n        ).forEach(function (link) {\n            link.hidden = false;\n            link.style.display = "";\n            link.title =\n                "Tổ " + data.team_number\n                + " · còn " + data.remaining_quota + " hộ";\n        });\n    })\n    .catch(function () {});\n    {% endif %}\n})();\n</script>\n<!-- === BAI_13B_12_V2_2_NEW_HOUSE_BUTTON_JS_END === -->\n'

CORE_COUNT_TABLES = (
    "communes",
    "schools",
    "users",
    "school_years",
    "survey_batches",
    "households",
    "survey_forms",
    "survey_form_investigators",
    "survey_investigation_teams",
    "survey_investigation_team_members",
    "survey_investigation_team_forms",
    "survey_person_year_records",
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text_value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text_value, encoding="utf-8")


def sqlite_backup(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def restore_database() -> None:
    if not DB_BACKUP.exists():
        return
    src = sqlite3.connect(str(DB_BACKUP))
    dst = sqlite3.connect(str(DB))
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def backup_file(path: Path) -> None:
    if not path.exists():
        return
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path, existed_before: bool) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, path)
    elif not existed_before and path.exists():
        path.unlink()


def db_state() -> dict:
    con = sqlite3.connect(str(DB))
    try:
        integrity = str(
            con.execute("PRAGMA integrity_check").fetchone()[0]
        )
        fk_count = len(
            con.execute("PRAGMA foreign_key_check").fetchall()
        )
        existing = {
            str(r[0])
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        counts = {}
        for table in CORE_COUNT_TABLES:
            if table in existing:
                counts[table] = int(
                    con.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                )
        cols = {
            str(r[1])
            for r in con.execute(
                "PRAGMA table_info(survey_person_year_records)"
            ).fetchall()
        }
        return {
            "integrity": integrity,
            "fk_count": fk_count,
            "counts": counts,
            "year_columns": cols,
            "tables": existing,
        }
    finally:
        con.close()


def migrate_db() -> None:
    con = sqlite3.connect(str(DB))
    try:
        con.execute("PRAGMA foreign_keys=ON")
        for statement in SCHEMA_SQL:
            con.execute(statement)
        con.commit()
    finally:
        con.close()


def patch_menu(text_value: str) -> str:
    if MARK_HIDE_UPDATE not in text_value:
        marker = "{# === BAI_13B_9_V1A_MENU === #}"
        start = text_value.find(marker)
        if start < 0:
            raise RuntimeError("Menu thiếu BAI_13B_9_V1A_MENU.")
        end = min(len(text_value), start + 800)
        window = text_value[start:end]
        old = "{% if nguoi_dung and nguoi_dung.role_code != 'GIAO_VIEN' %}"
        if old not in window:
            raise RuntimeError("Không tìm thấy điều kiện menu cập nhật hộ.")
        new = (
            "{# === " + MARK_HIDE_UPDATE + "_START === #}\n"
            "{% if nguoi_dung and nguoi_dung.role_code not in ['GIAO_VIEN', 'XA'] %}"
        )
        window = window.replace(old, new, 1)
        link_pos = window.find("/dieu-tra/cap-nhat-ho-dan")
        endif_pos = window.find("{% endif %}", link_pos)
        if link_pos < 0 or endif_pos < 0:
            raise RuntimeError("Không xác định được block cập nhật hộ.")
        window = (
            window[:endif_pos]
            + "{# === " + MARK_HIDE_UPDATE + "_END === #}\n"
            + window[endif_pos:]
        )
        text_value = text_value[:start] + window + text_value[end:]

    if MARK_MENU not in text_value:
        start = text_value.find("{% elif menu_role == 'XA' %}")
        end = text_value.find("{% elif menu_role == 'TRUONG' %}", start)
        if start < 0 or end < 0:
            raise RuntimeError("Không tìm thấy block Danh mục cấp Xã.")
        window = text_value[start:end]
        closing = "                </div>\n            </div>\n"
        pos = window.rfind(closing)
        if pos < 0:
            raise RuntimeError("Không tìm thấy điểm chèn menu địa bàn.")
        link = (
            "                    {# === " + MARK_MENU + "_START === #}\n"
            "                    <a href=\"/dieu-tra/phan-cong-to-dieu-tra/dia-ban\" "
            "role=\"menuitem\">1.3. Danh mục thôn/xóm/khối/tổ/bản</a>\n"
            "                    {# === " + MARK_MENU + "_END === #}\n"
        )
        window = window[:pos] + link + window[pos:]
        text_value = text_value[:start] + window + text_value[end:]

    return text_value


def patch_surveys(text_value: str) -> str:
    if MARK_SURVEY_SCOPE in text_value:
        return text_value

    fn_start = text_value.find("def tao_bo_loc_dot_theo_nguoi_dung(")
    fn_end = text_value.find(
        "def tao_bo_loc_phieu_theo_nguoi_dung(",
        fn_start,
    )
    if fn_start < 0 or fn_end < 0:
        raise RuntimeError("Không tìm thấy hàm lọc đợt.")
    window = text_value[fn_start:fn_end]
    if OLD_SURVEY_TEACHER_FILTER not in window:
        raise RuntimeError("Nhánh lọc đợt GV khác bản khảo sát.")
    window = window.replace(
        OLD_SURVEY_TEACHER_FILTER,
        NEW_SURVEY_TEACHER_FILTER,
        1,
    )
    return text_value[:fn_start] + window + text_value[fn_end:]


def patch_access(text_value: str) -> str:
    if MARK_HIDE_UPDATE not in text_value:
        action_start = text_value.find(
            "# === BAI_13B_9_V1A_ACCESS_ACTION_START ==="
        )
        action_end = text_value.find(
            "# === BAI_13B_9_V1A_ACCESS_ACTION_END ===",
            action_start,
        )
        if action_start < 0 or action_end < 0:
            raise RuntimeError("Thiếu access action cập nhật hộ.")
        window = text_value[action_start:action_end]
        target = "                COMMUNE_ROLE_CODE,\n"
        if target not in window:
            raise RuntimeError("Không thấy quyền XA trong action cập nhật hộ.")
        window = window.replace(
            target,
            "                # " + MARK_HIDE_UPDATE + ": bỏ quyền Xã.\n",
            1,
        )
        text_value = (
            text_value[:action_start]
            + window
            + text_value[action_end:]
        )

        scope_start = text_value.find(
            "# === BAI_13B_9_V1A_ACCESS_SCOPE_START ==="
        )
        scope_end = text_value.find(
            "# === BAI_13B_9_V1A_ACCESS_SCOPE_END ===",
            scope_start,
        )
        if scope_start < 0 or scope_end < 0:
            raise RuntimeError("Thiếu access scope cập nhật hộ.")
        window = text_value[scope_start:scope_end]
        if target not in window:
            raise RuntimeError("Không thấy quyền XA trong scope cập nhật hộ.")
        window = window.replace(
            target,
            "                # " + MARK_HIDE_UPDATE + ": chặn Xã.\n",
            1,
        )
        text_value = (
            text_value[:scope_start]
            + window
            + text_value[scope_end:]
        )

    if MARK_ACCESS + "_BATCH_SCOPE" not in text_value:
        fn_start = text_value.find("def _pc_batch_in_account_scope(")
        fn_end = text_value.find("\n\ndef ", fn_start + 10)
        if fn_start < 0 or fn_end < 0:
            raise RuntimeError("Thiếu _pc_batch_in_account_scope.")
        window = text_value[fn_start:fn_end]
        teacher_start = window.find(
            "    if role_code == TEACHER_ROLE_CODE:"
        )
        teacher_end = window.find("\n    return False", teacher_start)
        if teacher_start < 0 or teacher_end < 0:
            raise RuntimeError("Không xác định được nhánh GV batch scope.")
        teacher_block = window[teacher_start:teacher_end]
        old_return = "        return allowed is not None"
        if old_return not in teacher_block:
            raise RuntimeError("Nhánh GV batch scope khác khảo sát.")
        teacher_block = teacher_block.replace(
            old_return,
            ACCESS_BATCH_EXTRA,
            1,
        )
        window = (
            window[:teacher_start]
            + teacher_block
            + window[teacher_end:]
        )
        text_value = (
            text_value[:fn_start]
            + window
            + text_value[fn_end:]
        )

    if MARK_ACCESS + "_LATEST_BATCH" not in text_value:
        if OLD_ACCESS_LATEST_SQL not in text_value:
            raise RuntimeError("Không tìm thấy SQL batch mới nhất của GV.")
        text_value = text_value.replace(
            OLD_ACCESS_LATEST_SQL,
            NEW_ACCESS_LATEST_SQL,
            1,
        )

    if MARK_ACCESS + "_ACTION" not in text_value:
        anchor = (
            "        # Phân công điều tra được mở cho "
            "ADMIN/SO, Xã/phường và Trường."
        )
        pos = text_value.find(anchor)
        if pos < 0:
            raise RuntimeError("Không tìm thấy điểm chèn access action V2.2.")
        text_value = (
            text_value[:pos]
            + ACCESS_ACTION_BLOCK
            + text_value[pos:]
        )

    if MARK_ACCESS + "_SCOPE" not in text_value:
        anchor = "        # === BAI_13B_10_V1_ACCESS_START ==="
        pos = text_value.find(anchor)
        if pos < 0:
            raise RuntimeError("Không tìm thấy điểm chèn access scope V2.2.")
        text_value = (
            text_value[:pos]
            + ACCESS_SCOPE_BLOCK
            + text_value[pos:]
        )

    return text_value


def patch_team_router(text_value: str) -> str:
    if MARK_FINALIZE not in text_value:
        if OLD_FINALIZE_NO_FORMS not in text_value:
            raise RuntimeError("Không tìm thấy block chốt tổ không có phiếu.")
        text_value = text_value.replace(
            OLD_FINALIZE_NO_FORMS,
            NEW_FINALIZE_NO_FORMS,
            1,
        )

    if "BAI_13B_12_V2_2_AREA_WORKFLOW_START" not in text_value:
        text_value = (
            text_value.rstrip()
            + "\n\n"
            + AREA_ROUTER_BLOCK.strip()
            + "\n"
        )

    if "BAI_13B_12_V2_2_TEAM_NEW_HOUSEHOLD_START" not in text_value:
        text_value = (
            text_value.rstrip()
            + "\n\n"
            + TEAM_NEW_HOUSE_BLOCK.strip()
            + "\n"
        )

    return text_value


def patch_households_template(text_value: str) -> str:
    if MARK_HOUSE_BUTTON in text_value:
        return text_value

    mobile_anchor = '<div class="pc-gv-v18-assignments-inner">'
    if mobile_anchor not in text_value:
        raise RuntimeError("Không tìm thấy container mobile GV.")
    text_value = text_value.replace(
        mobile_anchor,
        mobile_anchor + MOBILE_BUTTON,
        1,
    )

    toolbar_anchor = "            {% if co_quyen_xem_tien_do %}\n"
    pos = text_value.find(toolbar_anchor)
    if pos < 0:
        raise RuntimeError("Không tìm thấy điểm chèn nút desktop.")
    text_value = (
        text_value[:pos]
        + DESKTOP_BUTTON
        + text_value[pos:]
    )

    body_pos = text_value.rfind("</body>")
    if body_pos < 0:
        raise RuntimeError("households.html thiếu </body>.")
    text_value = (
        text_value[:body_pos]
        + HOUSE_BUTTON_JS
        + text_value[body_pos:]
    )
    return text_value


def verify_source() -> None:
    menu = read_text(MENU)
    surveys = read_text(SURVEYS)
    team = read_text(TEAM_ROUTER)
    access = read_text(ACCESS)
    households = read_text(HOUSEHOLDS_TEMPLATE)

    for token in (
        MARK_MENU,
        MARK_HIDE_UPDATE,
        "1.3. Danh mục thôn/xóm/khối/tổ/bản",
    ):
        if token not in menu:
            raise RuntimeError("Menu thiếu: " + token)

    if "2.2.8." in menu:
        raise RuntimeError("Phát hiện menu 2.2.8 ngoài yêu cầu.")

    for token in (
        MARK_SURVEY_SCOPE,
        "team_membership = text(",
    ):
        if token not in surveys:
            raise RuntimeError("surveys.py thiếu: " + token)

    for token in (
        "BAI_13B_12_V2_2_AREA_WORKFLOW_START",
        "BAI_13B_12_V2_2_TEAM_NEW_HOUSEHOLD_START",
        MARK_FINALIZE,
        '@router.get("/dia-ban"',
        '@router.get("/nhap-ho-moi/{batch_id}/quyen")',
    ):
        if token not in team:
            raise RuntimeError("team router thiếu: " + token)

    for token in (
        MARK_ACCESS + "_BATCH_SCOPE",
        MARK_ACCESS + "_LATEST_BATCH",
        MARK_ACCESS + "_ACTION",
        MARK_ACCESS + "_SCOPE",
        MARK_HIDE_UPDATE,
    ):
        if token not in access:
            raise RuntimeError("access_control.py thiếu: " + token)

    for token in (
        MARK_HOUSE_BUTTON,
        "➕ Điều tra mới – Nhập hộ dân mới",
        "b1322-new-household-link",
    ):
        if token not in households:
            raise RuntimeError("households.html thiếu: " + token)

    if (
        "highest_completed_grade" not in surveys
        or "education_attainment_level" not in surveys
    ):
        raise RuntimeError("V2.1 trình độ toàn dân không còn đầy đủ.")

    ast.parse(surveys)
    ast.parse(team)
    ast.parse(access)
    py_compile.compile(str(SURVEYS), doraise=True)
    py_compile.compile(str(TEAM_ROUTER), doraise=True)
    py_compile.compile(str(ACCESS), doraise=True)

    env = Environment()
    env.parse(menu)
    env.parse(households)
    env.parse(read_text(AREA_TEMPLATE_PATH))
    env.parse(read_text(NEW_HOUSE_TEMPLATE_PATH))


def verify_db(before: dict) -> dict:
    after = db_state()
    for table in (
        "survey_commune_areas",
        "survey_team_area_assignments",
        "survey_form_areas",
    ):
        if table not in after["tables"]:
            raise RuntimeError("DB thiếu bảng mới: " + table)

    if after["integrity"].lower() != "ok":
        raise RuntimeError("integrity_check không đạt.")
    if after["fk_count"] != 0:
        raise RuntimeError("foreign_key_check có lỗi.")
    if after["counts"] != before["counts"]:
        raise RuntimeError("Số dòng bảng lõi thay đổi ngoài dự kiến.")

    for col in (
        "highest_completed_grade",
        "education_attainment_level",
    ):
        if col not in after["year_columns"]:
            raise RuntimeError("V2.1 thiếu cột: " + col)

    return after


def clear_cache() -> None:
    for cache in APP.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def main() -> int:
    global PROJECT, APP, DB, EXPORTS
    global MENU, HOUSEHOLDS_TEMPLATE, AREA_TEMPLATE_PATH
    global NEW_HOUSE_TEMPLATE_PATH, SURVEYS, TEAM_ROUTER, ACCESS
    global BACKUP, DB_BACKUP, REPORT

    if not APP.is_dir():
        PROJECT = Path.cwd().resolve()
        APP = PROJECT / "app"
        DB = PROJECT / "data" / "phocap.db"
        EXPORTS = PROJECT / "exports"
        MENU = APP / "templates" / "partials" / "dropdown_menu_v1.html"
        HOUSEHOLDS_TEMPLATE = APP / "templates" / "surveys" / "households.html"
        AREA_TEMPLATE_PATH = APP / "templates" / "survey_teams" / "commune_areas_v2_2.html"
        NEW_HOUSE_TEMPLATE_PATH = APP / "templates" / "surveys" / "new_household_team_v2_2.html"
        SURVEYS = APP / "routers" / "surveys.py"
        TEAM_ROUTER = APP / "routers" / "survey_team_registration.py"
        ACCESS = APP / "access_control.py"
        BACKUP = EXPORTS / f"backup_bai_13b_12_v2_2_{STAMP}"
        DB_BACKUP = BACKUP / "phocap.db"
        REPORT = EXPORTS / f"bao_cao_cai_bai_13b_12_v2_2_{STAMP}.txt"

    print("=" * 120)
    print(
        "BÀI 13B-12 V2.2 - DANH MỤC ĐỊA BÀN + "
        "GIAO ĐỊA BÀN/CHỈ TIÊU + TỔ TẠO HỘ"
    )
    print("=" * 120)
    print("Dự án:", PROJECT)
    print()

    for path in (
        DB,
        MENU,
        HOUSEHOLDS_TEMPLATE,
        SURVEYS,
        TEAM_ROUTER,
        ACCESS,
    ):
        if not path.exists():
            print("DỪNG AN TOÀN: thiếu", path)
            return 2

    before = db_state()
    print("integrity_check:", before["integrity"])
    print("foreign_key_check:", before["fk_count"], "lỗi")
    print("survey_batches hiện có:", before["counts"].get("survey_batches", 0))
    print()

    if before["integrity"].lower() != "ok" or before["fk_count"] != 0:
        print("DỪNG: database chưa đạt kiểm tra.")
        return 3

    for col in (
        "highest_completed_grade",
        "education_attainment_level",
    ):
        if col not in before["year_columns"]:
            print("DỪNG: chưa có V2.1, thiếu", col)
            return 4

    team_before = read_text(TEAM_ROUTER)
    surveys_before = read_text(SURVEYS)
    access_before = read_text(ACCESS)
    menu_before = read_text(MENU)
    households_before = read_text(HOUSEHOLDS_TEMPLATE)

    checks = (
        ('@router.post("/lap-to/chot-gui")', "survey_team_registration.py", team_before),
        ("def tao_bo_loc_dot_theo_nguoi_dung(", "surveys.py", surveys_before),
        ("# === BAI_13B_9_V1A_ACCESS_ACTION_START ===", "access_control.py", access_before),
        ("# === BAI_13B_10_V1_ACCESS_START ===", "access_control.py", access_before),
        ("2.2.1. Danh sách hộ dân / phiếu được giao", "dropdown_menu_v1.html", menu_before),
        ("openHouseholdDialog()", "households.html", households_before),
    )
    for token, source_name, source_text in checks:
        if token not in source_text:
            print("DỪNG AN TOÀN:", source_name, "thiếu:", token)
            return 5

    if (
        MARK_MENU in menu_before
        and MARK_SURVEY_SCOPE in surveys_before
        and "BAI_13B_12_V2_2_AREA_WORKFLOW_START" in team_before
        and MARK_ACCESS + "_SCOPE" in access_before
        and MARK_HOUSE_BUTTON in households_before
        and {
            "survey_commune_areas",
            "survey_team_area_assignments",
            "survey_form_areas",
        }.issubset(before["tables"])
    ):
        print("V2.2 đã được cài đầy đủ. Không cài lặp.")
        return 0

    try:
        menu_new = patch_menu(menu_before)
        surveys_new = patch_surveys(surveys_before)
        access_new = patch_access(access_before)
        team_new = patch_team_router(team_before)
        households_new = patch_households_template(households_before)

        ast.parse(surveys_new)
        ast.parse(access_new)
        ast.parse(team_new)

        env = Environment()
        env.parse(menu_new)
        env.parse(households_new)
        env.parse(AREA_TEMPLATE)
        env.parse(NEW_HOUSE_TEMPLATE)
    except Exception as exc:
        print(
            "DỪNG AN TOÀN TRƯỚC KHI CÀI:",
            type(exc).__name__ + ":",
            exc,
        )
        return 6

    EXPORTS.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=False)

    touched = (
        MENU,
        HOUSEHOLDS_TEMPLATE,
        AREA_TEMPLATE_PATH,
        NEW_HOUSE_TEMPLATE_PATH,
        SURVEYS,
        TEAM_ROUTER,
        ACCESS,
    )
    existed = {path: path.exists() for path in touched}

    for path in touched:
        backup_file(path)
    sqlite_backup(DB, DB_BACKUP)

    print("Backup:", BACKUP)
    print()

    try:
        write_text(MENU, menu_new)
        write_text(SURVEYS, surveys_new)
        write_text(ACCESS, access_new)
        write_text(TEAM_ROUTER, team_new)
        write_text(HOUSEHOLDS_TEMPLATE, households_new)
        write_text(AREA_TEMPLATE_PATH, AREA_TEMPLATE)
        write_text(NEW_HOUSE_TEMPLATE_PATH, NEW_HOUSE_TEMPLATE)

        migrate_db()
        verify_source()
        after = verify_db(before)
        clear_cache()
    except Exception as exc:
        print()
        print("CÓ LỖI - ĐANG ROLLBACK SOURCE + DATABASE...")
        print(type(exc).__name__ + ":", exc)

        for path in touched:
            restore_file(path, existed_before=existed[path])
        restore_database()
        clear_cache()

        print("ĐÃ KHÔI PHỤC.")
        print("Backup:", BACKUP)
        return 9

    report_lines = [
        "=" * 120,
        "BÁO CÁO CÀI BÀI 13B-12 V2.2",
        "=" * 120,
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Dự án: {PROJECT}",
        "",
        "ĐÃ CÀI:",
        "1. Không tạo menu 2.2.8.",
        "2. Ẩn/chặn 'Cập nhật dữ liệu hộ dân' đối với Xã.",
        "3. Thêm 1.3. Danh mục thôn/xóm/khối/tổ/bản cho cấp Xã.",
        "4. Thêm survey_commune_areas.",
        "5. Thêm survey_team_area_assignments.",
        "6. Thêm survey_form_areas.",
        "7. Theo dõi Số hộ dự kiến / Đã nhập / Còn thiếu / %.",
        "8. Cho Xã chia đều/chỉnh chỉ tiêu cho từng tổ.",
        "9. Cho chốt/gửi tổ chưa có phiếu nếu đã giao đủ địa bàn/chỉ tiêu.",
        "10. GV thuộc tổ SENT được thấy batch dù chưa có phiếu.",
        "11. Nút '➕ Điều tra mới – Nhập hộ dân mới' tại 2.2.1.",
        "12. Hộ mới tự tạo phiếu, gắn địa bàn, team_forms và đủ 3 thành viên.",
        "13. Sau tạo hộ chuyển thẳng sang Nhập nhanh.",
        "",
        "GIỮ NGUYÊN:",
        "- Quy trình trường gửi GV; tổ 1 MN + 1 TH + 1 THCS.",
        "- survey_investigation_team_forms / survey_form_investigators.",
        "- Nhập nhanh, giao phiếu, khóa/mở.",
        "- PCGD, XMC và V2.1 trình độ toàn dân.",
        "",
        f"survey_batches trước/sau: {before['counts'].get('survey_batches', 0)} / {after['counts'].get('survey_batches', 0)}",
        f"households trước/sau: {before['counts'].get('households', 0)} / {after['counts'].get('households', 0)}",
        f"survey_forms trước/sau: {before['counts'].get('survey_forms', 0)} / {after['counts'].get('survey_forms', 0)}",
        f"integrity_check: {after['integrity']}",
        f"foreign_key_check: {after['fk_count']} lỗi",
        f"Backup: {BACKUP}",
    ]
    REPORT.write_text(
        "\n".join(report_lines) + "\n",
        encoding="utf-8-sig",
    )

    print("=" * 120)
    print("CÀI ĐẶT THÀNH CÔNG BÀI 13B-12 V2.2")
    print("=" * 120)
    print(" - Danh mục địa bàn + số hộ dự kiến.")
    print(" - Giao địa bàn/chỉ tiêu cho tổ.")
    print(" - Chốt tổ trước khi có hộ.")
    print(" - Tổ SENT mới có nút Điều tra mới – Nhập hộ dân mới.")
    print(" - Hộ mới tự gắn đủ 3 thành viên và chuyển Nhập nhanh.")
    print(" - Không tạo 2.2.8; không tạo dữ liệu giả định.")
    print()
    print("Backup:", BACKUP)
    print("Báo cáo:", REPORT)
    print()
    print(
        "LƯU Ý: nếu survey_batches đang = 0, sau cài Sở cần "
        "khởi tạo lại năm học 2026-2027 trước khi thử ghép/giao tổ."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
