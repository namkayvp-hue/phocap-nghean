# -*- coding: utf-8 -*-
r'''
V9.2.1 - KHÓA AN TOÀN GIAO DIỆN CHỌN TRƯỜNG NGUỒN / TRƯỜNG ĐÍCH
=================================================================

Chỉ sửa template:
    C:\PhoCap\app\templates\data_tools\school_merger.html

KHÔNG sửa database.
KHÔNG đổi route.
KHÔNG đổi menu.
KHÔNG đổi service sáp nhập đã cài V9.2.

Bổ sung:
1. Trường nguồn đã khóa vẫn hiển thị nếu bật "Hiện cả trường đã khóa",
   nhưng OPTION bị disabled, chỉ để đối chiếu.
2. Trường đích chỉ hiển thị trường đang hoạt động.
3. Sau khi chọn trường nguồn:
   - trường đích trùng với nguồn bị disabled;
   - trường đích khác cấp học với bất kỳ nguồn nào bị disabled.
4. Thêm hướng dẫn trực tiếp trên màn hình.

CHẠY:
    cd C:\PhoCap
    .\.venv\Scripts\python.exe .\cai_dat_an_toan_chon_nguon_dich_sap_nhap_v9_2_1.py
'''

from __future__ import annotations

import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\PhoCap")
TEMPLATE = ROOT / "app" / "templates" / "data_tools" / "school_merger.html"
EXPORTS = ROOT / "exports"

MARKER = "V9.2.1-SAFE-SOURCE-TARGET"

OLD_NOTE = '''<div class="merge-note info">Có thể chọn nhiều trường nguồn để nhập vào một trường đích trong cùng một lần. Trường nguồn phải đang hoạt động khi thực hiện thật.</div>'''

NEW_NOTE = '''<!-- V9.2.1-SAFE-SOURCE-TARGET -->
        <div class="merge-note info">
            Có thể chọn nhiều trường nguồn để nhập vào một trường đích trong cùng một lần.
            <strong>Trường đã khóa chỉ hiển thị để đối chiếu và không thể chọn làm nguồn.</strong>
            Trường đích luôn phải đang hoạt động. Sau khi chọn nguồn, hệ thống sẽ tự vô hiệu hóa
            các trường đích trùng nguồn hoặc không phù hợp cấp học.
        </div>'''

OLD_SOURCE = '''<select name="source_school_ids" multiple required>
                        {% for s in schools %}
                        <option value="{{ s.id }}">{{ s.name }} · {{ s.code }} · {{ s.level_text }}{% if not s.is_active %} · ĐÃ KHÓA{% endif %}</option>
                        {% endfor %}
                    </select>
                    <div class="muted-text">Windows: giữ Ctrl để chọn nhiều trường.</div>'''

NEW_SOURCE = '''<select id="merge-source-schools" name="source_school_ids" multiple required>
                        {% for s in schools %}
                        <option
                            value="{{ s.id }}"
                            data-levels="{{ s.levels|join(',') }}"
                            data-active="{{ 1 if s.is_active else 0 }}"
                            {% if not s.is_active %}disabled{% endif %}
                        >{{ s.name }} · {{ s.code }} · {{ s.level_text }}{% if not s.is_active %} · ĐÃ KHÓA · CHỈ XEM{% endif %}</option>
                        {% endfor %}
                    </select>
                    <div class="muted-text">
                        Windows: giữ Ctrl để chọn nhiều trường.
                        Trường đã khóa được hiển thị để đối chiếu nhưng không thể chọn.
                    </div>'''

OLD_TARGET = '''<select name="target_school_id" size="12" required>
                        {% for s in schools %}
                        <option value="{{ s.id }}">{{ s.name }} · {{ s.code }} · {{ s.level_text }}{% if not s.is_active %} · ĐÃ KHÓA{% endif %}</option>
                        {% endfor %}
                    </select>'''

NEW_TARGET = '''<select id="merge-target-school" name="target_school_id" size="12" required>
                        {% for s in schools %}
                        {% if s.is_active %}
                        <option
                            value="{{ s.id }}"
                            data-levels="{{ s.levels|join(',') }}"
                        >{{ s.name }} · {{ s.code }} · {{ s.level_text }}</option>
                        {% endif %}
                        {% endfor %}
                    </select>
                    <div id="merge-target-hint" class="muted-text">
                        Chỉ hiển thị trường đang hoạt động. Nên chọn “Cấp học” ở bước 1 để danh sách ngắn và dễ kiểm tra.
                    </div>'''

SCRIPT = r'''
<script>
(function () {
    const source = document.getElementById("merge-source-schools");
    const target = document.getElementById("merge-target-school");
    const hint = document.getElementById("merge-target-hint");

    if (!source || !target) return;

    function levelSet(option) {
        return new Set(
            String(option.dataset.levels || "")
                .split(",")
                .map(x => x.trim().toUpperCase())
                .filter(Boolean)
        );
    }

    function overlaps(a, b) {
        if (!a.size || !b.size) return true;
        for (const item of a) {
            if (b.has(item)) return true;
        }
        return false;
    }

    function refreshTargets() {
        const selectedSources = Array.from(source.selectedOptions)
            .filter(opt => !opt.disabled);

        const selectedIds = new Set(selectedSources.map(opt => String(opt.value)));
        const sourceLevels = selectedSources.map(levelSet);

        let enabledCount = 0;

        Array.from(target.options).forEach(opt => {
            const targetLevels = levelSet(opt);

            const sameAsSource = selectedIds.has(String(opt.value));
            const compatibleWithAllSources = sourceLevels.every(
                srcLevels => overlaps(srcLevels, targetLevels)
            );

            opt.disabled = sameAsSource || !compatibleWithAllSources;

            if (!opt.disabled) enabledCount += 1;
            if (opt.selected && opt.disabled) opt.selected = false;
        });

        if (hint) {
            if (!selectedSources.length) {
                hint.textContent =
                    "Chỉ hiển thị trường đang hoạt động. Sau khi chọn nguồn, danh sách đích sẽ tự khóa các trường trùng nguồn/khác cấp.";
            } else if (enabledCount === 0) {
                hint.textContent =
                    "Không còn trường đích phù hợp với toàn bộ nguồn đã chọn. Kiểm tra lại cấp học hoặc bỏ bớt trường nguồn.";
            } else {
                hint.textContent =
                    "Có " + enabledCount + " trường đích đang hoạt động phù hợp với nguồn đã chọn.";
            }
        }
    }

    source.addEventListener("change", refreshTargets);
    refreshTargets();
})();
</script>
'''

def main() -> None:
    if not TEMPLATE.exists():
        print(f"KHÔNG TÌM THẤY TEMPLATE: {TEMPLATE}")
        sys.exit(2)

    text = TEMPLATE.read_text(encoding="utf-8")

    if MARKER in text:
        print("=" * 100)
        print("V9.2.1 ĐÃ ĐƯỢC CÀI TRƯỚC ĐÓ")
        print("=" * 100)
        print("Database: KHÔNG THAY ĐỔI")
        return

    missing = []
    for name, needle in (
        ("ghi chú", OLD_NOTE),
        ("danh sách nguồn", OLD_SOURCE),
        ("danh sách đích", OLD_TARGET),
        ("thẻ </body>", "</body>"),
    ):
        if needle not in text:
            missing.append(name)

    if missing:
        print("=" * 100)
        print("DỪNG AN TOÀN - TEMPLATE KHÔNG KHỚP V9.2")
        print("=" * 100)
        print("Không tìm thấy:", ", ".join(missing))
        print("Không sửa file.")
        sys.exit(3)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = EXPORTS / f"backup_sap_nhap_v9_2_1_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(TEMPLATE, backup_dir / "school_merger.html")

    new_text = text
    new_text = new_text.replace(OLD_NOTE, NEW_NOTE, 1)
    new_text = new_text.replace(OLD_SOURCE, NEW_SOURCE, 1)
    new_text = new_text.replace(OLD_TARGET, NEW_TARGET, 1)
    new_text = new_text.replace("</body>", SCRIPT + "\n</body>", 1)

    checks = (
        MARKER,
        'id="merge-source-schools"',
        'id="merge-target-school"',
        'data-levels=',
        "refreshTargets",
    )
    for item in checks:
        if item not in new_text:
            print(f"DỪNG: nội dung sau vá thiếu marker {item!r}")
            sys.exit(4)

    TEMPLATE.write_text(new_text, encoding="utf-8")

    parse_result = "SKIP"
    try:
        from jinja2 import Environment
        Environment().parse(new_text)
        parse_result = "PASS"
    except ImportError:
        parse_result = "SKIP - jinja2 chưa có trong Python chạy installer"
    except Exception as exc:
        shutil.copy2(backup_dir / "school_merger.html", TEMPLATE)
        print("=" * 100)
        print("LỖI JINJA - ĐÃ TỰ KHÔI PHỤC TEMPLATE CŨ")
        print("=" * 100)
        print(repr(exc))
        sys.exit(5)

    report = backup_dir / "00_KET_QUA_CAI_DAT_V9_2_1.txt"
    report.write_text(
        "\n".join([
            "V9.2.1 - KHÓA AN TOÀN CHỌN NGUỒN/ĐÍCH",
            "=" * 80,
            "STATUS=SUCCESS",
            f"Template={TEMPLATE}",
            f"Backup={backup_dir / 'school_merger.html'}",
            f"Jinja parse={parse_result}",
            "Database=KHÔNG THAY ĐỔI",
            "",
            "Đã bổ sung:",
            "- Trường nguồn khóa: hiển thị nhưng disabled.",
            "- Trường đích: chỉ trường active.",
            "- Đích trùng nguồn: tự disabled.",
            "- Đích khác cấp: tự disabled.",
        ]),
        encoding="utf-8",
    )

    zip_path = ROOT / f"ket_qua_cai_dat_sap_nhap_v9_2_1_{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(report, arcname=report.name)
        zf.write(
            backup_dir / "school_merger.html",
            arcname="school_merger_TRUOC_V9_2_1.html",
        )
        zf.writestr("school_merger_SAU_V9_2_1.html", new_text)

    print("=" * 100)
    print("CÀI ĐẶT V9.2.1 THÀNH CÔNG")
    print("=" * 100)
    print("Database: KHÔNG THAY ĐỔI")
    print(f"Backup template: {backup_dir}")
    print(f"Jinja parse: {parse_result}")
    print("Đã khóa chọn trường nguồn đã khóa.")
    print("Trường đích chỉ còn trường đang hoạt động.")
    print("Đích trùng nguồn/khác cấp sẽ tự bị vô hiệu hóa.")
    print(f"ZIP kết quả: {zip_path}")


if __name__ == "__main__":
    main()
