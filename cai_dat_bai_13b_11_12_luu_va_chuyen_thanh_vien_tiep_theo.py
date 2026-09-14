from __future__ import annotations

import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TARGET = PROJECT / "app" / "templates" / "surveys" / "year_records.html"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_12_{STAMP}"

MARK_START = "<!-- === BAI_13B_11_12_SAVE_NEXT_PERSON_START === -->"
MARK_END = "<!-- === BAI_13B_11_12_SAVE_NEXT_PERSON_END === -->"

OLD_BUTTON = '                <button\n                    class="button button-primary"\n                    type="submit"\n                    style="width:100%;margin-top:17px;"\n                >\n                    Lưu thông tin năm học\n                </button>'
NEW_BUTTON = '                <button\n                    class="button button-primary"\n                    type="submit"\n                    style="width:100%;margin-top:17px;"\n                >\n                    {% if nguoi_dung.role_code == \'GIAO_VIEN\' %}\n                        {% if next_person_url %}\n                            Lưu và chuyển thành viên tiếp theo\n                        {% else %}\n                            Lưu thành viên cuối\n                        {% endif %}\n                    {% else %}\n                        Lưu thông tin năm học\n                    {% endif %}\n                </button>'
AUTO_BLOCK = '<!-- === BAI_13B_11_12_SAVE_NEXT_PERSON_START === -->\n{% if nguoi_dung.role_code == \'GIAO_VIEN\' and year_record_saved %}\n    {% if next_person_url %}\n        <div id="pc-auto-next-person">\n            ✓ Đã lưu {{ person.full_name }}. Đang chuyển sang thành viên tiếp theo...\n        </div>\n        <script>\n        (function () {\n            var nextUrl = {{ next_person_url | tojson }};\n            if (!nextUrl) return;\n            window.setTimeout(function () {\n                window.location.replace(nextUrl);\n            }, 450);\n        })();\n        </script>\n    {% else %}\n        <div id="pc-last-person-message">\n            ✓ Đã lưu. Đây là thành viên cuối cùng của hộ.\n        </div>\n        <script>\n        (function () {\n            window.setTimeout(function () {\n                alert("Đã lưu. Đây là thành viên cuối cùng của hộ.");\n            }, 120);\n        })();\n        </script>\n    {% endif %}\n{% endif %}\n<!-- === BAI_13B_11_12_SAVE_NEXT_PERSON_END === -->'


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def backup_source() -> None:
    dst = BACKUP / TARGET.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TARGET, dst)


def restore_source() -> None:
    src = BACKUP / TARGET.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, TARGET)


def patch(text: str) -> str:
    if MARK_START in text:
        print(" - Bài 13B-11.12 đã có sẵn, không chèn lặp.")
        return text

    if text.count(OLD_BUTTON) != 1:
        raise RuntimeError(
            "Không tìm thấy đúng 1 nút 'Lưu thông tin năm học' theo source đã khảo sát."
        )

    text = text.replace(OLD_BUTTON, NEW_BUTTON, 1)

    form_start = text.find('id="year_record_form"')
    if form_start < 0:
        raise RuntimeError("Không tìm thấy form year_record_form.")

    form_end = text.find("</form>", form_start)
    if form_end < 0:
        raise RuntimeError("Không tìm thấy </form> của year_record_form.")

    form_end += len("</form>")

    text = text[:form_end] + "\n\n" + AUTO_BLOCK + "\n" + text[form_end:]
    return text


def verify(text: str) -> None:
    required = [
        MARK_START,
        MARK_END,
        "Lưu và chuyển thành viên tiếp theo",
        "Lưu thành viên cuối",
        "Đây là thành viên cuối cùng của hộ",
        "window.location.replace(nextUrl)",
        "next_person_url | tojson",
        "year_record_saved",
        'id="year_record_form"',
        "/nam-hoc/luu",
    ]

    for marker in required:
        if marker not in text:
            raise RuntimeError(f"Thiếu nội dung sau cài: {marker}")

    if text.count(MARK_START) != 1 or text.count(MARK_END) != 1:
        raise RuntimeError("Khối Bài 13B-11.12 bị lặp.")

    from jinja2 import Environment
    Environment().parse(text)


def main() -> int:
    print("=" * 112)
    print("BÀI 13B-11.12 - LƯU VÀ TỰ CHUYỂN THÀNH VIÊN TIẾP THEO")
    print("=" * 112)
    print()
    print("NGHIỆP VỤ:")
    print(" - Còn thành viên sau: Lưu và chuyển thành viên tiếp theo.")
    print(" - Sau khi lưu thành công: tự mở người kế tiếp trong cùng hộ.")
    print(" - Thành viên cuối: Lưu thành viên cuối.")
    print(" - Sau khi lưu người cuối: thông báo rõ thành viên cuối.")
    print()
    print("AN TOÀN:")
    print(" - Chỉ sửa year_records.html.")
    print(" - Không sửa router.")
    print(" - Không sửa database.")
    print(" - Không đổi thứ tự thành viên; dùng next_person_url có sẵn.")
    print()

    if not TARGET.exists():
        raise RuntimeError(f"Không tìm thấy: {TARGET}")

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_source()
    print("Backup source:", BACKUP)

    try:
        before = read_text(TARGET)
        after = patch(before)
        verify(after)
        write_text(TARGET, after)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Nút lưu/chuyển: OK")
        print(" - Tự chuyển next_person_url: OK")
        print(" - Thông báo thành viên cuối: OK")
        print(" - Jinja parse: OK")
        print(" - Router: KHÔNG THAY ĐỔI")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.12 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore_source()
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
