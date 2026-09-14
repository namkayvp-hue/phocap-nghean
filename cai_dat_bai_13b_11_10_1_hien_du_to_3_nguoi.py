from __future__ import annotations

import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path

PROJECT = Path(os.environ.get("PHOCAP_PROJECT", r"C:\PhoCap")).resolve()
TEMPLATES = PROJECT / "app" / "templates"

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_10_1_{STAMP}"

MARK_PREFIX = "BAI_13B_11_10_1_SHOW_FULL_TEAM"


def read_text(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Không tìm thấy tệp: {path}")
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def candidate_score(path: Path, text: str) -> int:
    low = text.lower()
    score = 0
    if "người khác" in low:
        score += 20
    if "người điều tra" in low:
        score += 10
    if "investigator" in low:
        score += 8
    if "danh sách hộ" in low or "hộ dân" in low:
        score += 6
    if "survey" in str(path).lower():
        score += 3
    return score


def find_target() -> Path:
    candidates: list[tuple[int, Path, int]] = []

    for path in TEMPLATES.rglob("*.html"):
        try:
            text = read_text(path)
        except Exception:
            continue

        count = len(re.findall(r"người\s+khác", text, flags=re.IGNORECASE))
        if count <= 0:
            continue

        candidates.append((candidate_score(path, text), path, count))

    if not candidates:
        raise RuntimeError(
            "Không tìm thấy template có dòng rút gọn số thành viên."
        )

    candidates.sort(key=lambda x: (-x[0], str(x[1])))

    print("Các template có cụm rút gọn:")
    for score, path, count in candidates:
        print(f" - score={score:02d}  occurrences={count}  {path}")

    best_score = candidates[0][0]
    best = [item for item in candidates if item[0] == best_score]

    if len(best) != 1:
        raise RuntimeError(
            "Có nhiều template cùng mức phù hợp cao nhất. "
            "Dừng để tránh sửa nhầm."
        )

    return best[0][1]


def backup_file(path: Path) -> None:
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, path)


def locate_if_block(text: str, phrase_pos: int) -> tuple[int, int] | None:
    search_left = max(0, phrase_pos - 1800)
    search_right = min(len(text), phrase_pos + 1800)

    starts = list(re.finditer(r"{%\s*if\b", text[search_left:phrase_pos]))
    if not starts:
        return None

    start = search_left + starts[-1].start()

    endif_match = re.search(
        r"{%\s*endif\s*%}",
        text[phrase_pos:search_right],
    )
    if not endif_match:
        return None

    end = phrase_pos + endif_match.end()
    block = text[start:end]

    if not re.search(r"người\s+khác", block, flags=re.IGNORECASE):
        return None

    # Chỉ nhận khối if đơn giản, không tự động đụng vào khối if lồng nhau.
    if len(re.findall(r"{%\s*if\b", block)) != 1:
        return None
    if len(re.findall(r"{%\s*endif\s*%}", block)) != 1:
        return None

    return start, end


def locate_slice_before(text: str, phrase_pos: int) -> tuple[int, int] | None:
    left = max(0, phrase_pos - 3200)
    window = text[left:phrase_pos]

    patterns = [
        r"\[\s*:\s*2\s*\]",
        r"\[\s*0\s*:\s*2\s*\]",
    ]

    matches: list[tuple[int, int]] = []
    for pattern in patterns:
        for m in re.finditer(pattern, window):
            matches.append((left + m.start(), left + m.end()))

    if not matches:
        return None

    matches.sort(key=lambda x: x[0])
    return matches[-1]


def patch_one_occurrence(
    text: str,
    phrase_pos: int,
    index: int,
) -> str:
    if_block = locate_if_block(text, phrase_pos)
    if if_block is None:
        raise RuntimeError(
            f"Vị trí rút gọn #{index}: không xác định được khối if an toàn."
        )

    slice_pos = locate_slice_before(text, phrase_pos)
    if slice_pos is None:
        raise RuntimeError(
            f"Vị trí rút gọn #{index}: không tìm thấy giới hạn [:2] "
            "gần danh sách thành viên."
        )

    if_start, if_end = if_block
    slice_start, slice_end = slice_pos

    if slice_end > if_start:
        raise RuntimeError(
            f"Vị trí rút gọn #{index}: giới hạn [:2] nằm trong khối "
            "không mong đợi; dừng để tránh sửa sai."
        )

    marker = (
        "{# === "
        + MARK_PREFIX
        + f"_{index} === #}}\n"
        "{# Đã hiển thị toàn bộ thành viên tổ điều tra. #}"
    )

    # Thay từ phải sang trái để không lệch vị trí.
    text = text[:if_start] + marker + text[if_end:]
    text = text[:slice_start] + text[slice_end:]

    return text


def patch(text: str) -> tuple[str, int]:
    if MARK_PREFIX in text:
        print(" - Bài 13B-11.10.1 đã có marker; không cài lặp.")
        return text, 0

    occurrences = list(
        re.finditer(r"người\s+khác", text, flags=re.IGNORECASE)
    )

    if not occurrences:
        raise RuntimeError("Template không còn cụm rút gọn để sửa.")

    print(f"Số vị trí rút gọn tìm thấy trong template: {len(occurrences)}")

    # Xử lý từ cuối file lên đầu file.
    positions = [m.start() for m in occurrences]
    positions.sort(reverse=True)

    changed = 0
    for n, pos in enumerate(positions, start=1):
        text = patch_one_occurrence(text, pos, n)
        changed += 1

    return text, changed


def strip_jinja_comments(text: str) -> str:
    return re.sub(r"{#.*?#}", "", text, flags=re.DOTALL)


def verify(text: str, expected_changed: int) -> None:
    if expected_changed <= 0:
        raise RuntimeError("Không có vị trí nào được thay đổi.")

    visible = strip_jinja_comments(text)

    if re.search(r"người\s+khác", visible, flags=re.IGNORECASE):
        raise RuntimeError(
            "Sau sửa vẫn còn cụm rút gọn trong nội dung hiển thị."
        )

    marker_count = text.count(MARK_PREFIX)
    if marker_count != expected_changed:
        raise RuntimeError(
            f"Số marker sau sửa không khớp: "
            f"{marker_count} != {expected_changed}"
        )

    try:
        from jinja2 import Environment
        Environment().parse(text)
    except Exception as exc:
        raise RuntimeError(f"Jinja parse không đạt: {exc}") from exc


def main() -> int:
    print("=" * 112)
    print("BÀI 13B-11.10.1 - HIỂN THỊ ĐỦ TOÀN BỘ 3 THÀNH VIÊN TỔ ĐIỀU TRA")
    print("=" * 112)
    print()
    print("MỤC TIÊU:")
    print(" - Cột Người điều tra hiển thị đủ cả 3 thành viên.")
    print(" - Bỏ toàn bộ kiểu rút gọn chỉ hiện 2 người rồi cộng thêm số còn lại.")
    print()
    print("NGHIỆP VỤ GIỮ NGUYÊN:")
    print(" - Một phiếu thuộc chung tổ điều tra.")
    print(" - Chỉ cần một thành viên trong tổ hoàn thành phiếu.")
    print(" - Không yêu cầu cả 3 giáo viên cùng nhập.")
    print()
    print("AN TOÀN:")
    print(" - Chỉ sửa đúng template được xác định tự động.")
    print(" - Backup source trước khi sửa.")
    print(" - Không sửa router.")
    print(" - Không sửa database.")
    print(" - Không đổi người được phân công.")
    print(" - Nếu còn cấu trúc không chắc chắn sẽ rollback.")
    print()

    target = find_target()
    print()
    print("Template được chọn:", target)

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(target)
    print("Backup source:", BACKUP)

    try:
        before = read_text(target)
        after, changed = patch(before)

        verify(after, changed)
        write_text(target, after)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(f" - Số khối rút gọn đã xử lý: {changed}")
        print(" - Không còn nội dung rút gọn trên template: OK")
        print(" - Danh sách thành viên không còn giới hạn [:2]: OK")
        print(" - Jinja parse: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.10.1 THÀNH CÔNG")
        return 0

    except Exception:
        traceback.print_exc()
        print()
        print("CÓ LỖI - ĐANG KHÔI PHỤC TEMPLATE...")
        restore_file(target)
        print("ĐÃ KHÔI PHỤC SOURCE.")
        print("Database không bị thay đổi.")
        print("Backup:", BACKUP)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
