# -*- coding: utf-8 -*-
r'''
V9.3.1 - LÀM RÕ Ý NGHĨA CỘT THÔNG TIN DỮ LIỆU
================================================

Chỉ sửa template:
    C:\PhoCap\app\templates\data_tools\school_merger.html

KHÔNG sửa database.
KHÔNG đổi route/service/menu.

Mục tiêu:
- Với plan APPROVED:
    số liệu = DỰ KIẾN hệ thống sẽ xử lý khi thực hiện.
- Với plan COMPLETED:
    số liệu = DỮ LIỆU HIỆN CÒN GẮN TẠI TRƯỜNG NGUỒN sau khi hoàn thành,
    KHÔNG phải số đã chuyển.
- Làm rõ phần lịch sử của chức năng dùng chung.
'''

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger.html"
EXPORTS = ROOT / "exports"

MARKER = "V9.3.1-DATA-INFO-SEMANTICS"

OLD_BLOCK = '''                    <td>
                        {% if p.effective_status == 'COMPLETED' %}
                        <div class="muted-text">Đã xử lý theo phương án; dữ liệu lịch sử vẫn giữ nguyên.</div>
                        {% endif %}
                        <div class="data-chips">
                            {% if selected_data_view in ['all','accounts'] %}
                            <span class="data-chip">Tài khoản: {{ p.data_summary.accounts }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','staff'] %}
                            <span class="data-chip">Đội ngũ: {{ p.data_summary.staff }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','classes'] %}
                            <span class="data-chip">Lớp: {{ p.data_summary.classes }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','students'] %}
                            <span class="data-chip">HS/enrollment: {{ p.data_summary.students }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','survey'] %}
                            <span class="data-chip">Điều tra: {{ p.data_summary.survey }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','other'] %}
                            <span class="data-chip">Khác: {{ p.data_summary.other }}</span>
                            {% endif %}
                        </div>
                        {% if selected_data_view == 'all' %}
                        <div class="muted-text" style="margin-top:5px">
                            Lịch sử giữ nguyên: {{ p.data_summary.historical }}
                        </div>
                        {% endif %}
                    </td>'''

NEW_BLOCK = '''                    <td>
                        <!-- V9.3.1-DATA-INFO-SEMANTICS -->
                        {% if p.effective_status == 'COMPLETED' %}
                        <div class="muted-text" style="margin-bottom:6px">
                            <strong>Dữ liệu hiện còn gắn tại trường nguồn sau khi hoàn thành</strong>
                            (không phải số lượng đã chuyển).
                        </div>
                        <div class="data-chips">
                            {% if selected_data_view in ['all','accounts'] %}
                            <span class="data-chip">TK còn tại nguồn: {{ p.data_summary.accounts }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','staff'] %}
                            <span class="data-chip">Đội ngũ còn tại nguồn: {{ p.data_summary.staff }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','classes'] %}
                            <span class="data-chip">Lớp còn tại nguồn: {{ p.data_summary.classes }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','students'] %}
                            <span class="data-chip">HS/enrollment còn tại nguồn: {{ p.data_summary.students }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','survey'] %}
                            <span class="data-chip">Điều tra còn tại nguồn: {{ p.data_summary.survey }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','other'] %}
                            <span class="data-chip">Khác còn tại nguồn: {{ p.data_summary.other }}</span>
                            {% endif %}
                        </div>
                        {% if selected_data_view == 'all' %}
                        <div class="muted-text" style="margin-top:5px">
                            Dòng lịch sử giữ nguyên tại trường nguồn: {{ p.data_summary.historical }}
                        </div>
                        {% endif %}
                        {% if p.note %}
                        <div class="muted-text" style="margin-top:5px">{{ p.note }}</div>
                        {% endif %}

                        {% else %}
                        <div class="muted-text" style="margin-bottom:6px">
                            <strong>Dự kiến dữ liệu sẽ được xử lý đồng bộ khi thực hiện phương án.</strong>
                        </div>
                        <div class="data-chips">
                            {% if selected_data_view in ['all','accounts'] %}
                            <span class="data-chip">Tài khoản sẽ xử lý: {{ p.data_summary.accounts }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','staff'] %}
                            <span class="data-chip">Đội ngũ sẽ xử lý: {{ p.data_summary.staff }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','classes'] %}
                            <span class="data-chip">Lớp sẽ xử lý: {{ p.data_summary.classes }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','students'] %}
                            <span class="data-chip">HS/enrollment sẽ xử lý: {{ p.data_summary.students }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','survey'] %}
                            <span class="data-chip">Điều tra sẽ xử lý: {{ p.data_summary.survey }}</span>
                            {% endif %}
                            {% if selected_data_view in ['all','other'] %}
                            <span class="data-chip">Khác sẽ xử lý: {{ p.data_summary.other }}</span>
                            {% endif %}
                        </div>
                        {% if selected_data_view == 'all' %}
                        <div class="muted-text" style="margin-top:5px">
                            Dòng lịch sử sẽ giữ nguyên: {{ p.data_summary.historical }}
                        </div>
                        {% endif %}
                        {% endif %}
                    </td>'''

OLD_HISTORY_EMPTY = '''        <p class="muted-text">Chưa có lần sáp nhập nào được thực hiện bằng chức năng dùng chung.</p>'''

NEW_HISTORY_EMPTY = '''        <p class="muted-text">
            Chưa có lần sáp nhập nào được thực hiện trực tiếp bằng chức năng dùng chung này.
            Các phương án đã hoàn thành trước khi tích hợp chức năng có thể vẫn được ghi nhận
            ở bảng phương án phía trên nhưng không có operation log tại đây.
        </p>'''


def main() -> None:
    if not TEMPLATE.exists():
        print(f"Không tìm thấy: {TEMPLATE}")
        sys.exit(2)

    text = TEMPLATE.read_text(encoding="utf-8")

    if MARKER in text:
        print("V9.3.1 đã được cài trước đó.")
        print("Database KHÔNG thay đổi.")
        return

    if OLD_BLOCK not in text:
        print("DỪNG: template không khớp V9.3 ở khối Thông tin dữ liệu.")
        print("Không sửa file.")
        sys.exit(3)

    if OLD_HISTORY_EMPTY not in text:
        print("DỪNG: template không khớp V9.3 ở khối lịch sử.")
        print("Không sửa file.")
        sys.exit(4)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = EXPORTS / f"backup_sap_nhap_v9_3_1_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup = backup_dir / TEMPLATE.name
    shutil.copy2(TEMPLATE, backup)

    new_text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    new_text = new_text.replace(OLD_HISTORY_EMPTY, NEW_HISTORY_EMPTY, 1)

    try:
        from jinja2 import Environment
        Environment().parse(new_text)
        jinja_status = "PASS"
    except ImportError:
        jinja_status = "SKIP"
    except Exception as exc:
        print("Lỗi Jinja, không ghi file:", repr(exc))
        sys.exit(5)

    TEMPLATE.write_text(new_text, encoding="utf-8")

    print("=" * 100)
    print("CÀI ĐẶT V9.3.1 THÀNH CÔNG")
    print("=" * 100)
    print("Database: KHÔNG THAY ĐỔI")
    print(f"Backup template: {backup}")
    print(f"Jinja parse: {jinja_status}")
    print("Plan COMPLETED: số liệu được ghi rõ là dữ liệu CÒN TẠI NGUỒN.")
    print("Plan APPROVED: số liệu được ghi rõ là DỰ KIẾN SẼ XỬ LÝ.")


if __name__ == "__main__":
    main()
