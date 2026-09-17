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
BACKUP = PROJECT / "exports" / f"backup_source_bai_13b_11_10_{STAMP}"

MARK_START = "{# === BAI_13B_11_10_SHOW_ALL_TEAM_MEMBERS_START === #}"
MARK_END = "{# === BAI_13B_11_10_SHOW_ALL_TEAM_MEMBERS_END === #}"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def score_candidate(path: Path, text: str) -> int:
    low = text.lower()
    score = 0
    if "người khác" in low:
        score += 10
    if "người điều tra" in low:
        score += 5
    if "investigator" in low:
        score += 4
    if "survey" in str(path).lower():
        score += 2
    if "household" in low or "hộ dân" in low or "phiếu điều tra" in low:
        score += 3
    return score


def find_target() -> Path:
    candidates = []

    for path in TEMPLATES.rglob("*.html"):
        try:
            text = read_text(path)
        except Exception:
            continue

        if "người khác" not in text.lower():
            continue

        candidates.append((score_candidate(path, text), path))

    if not candidates:
        raise RuntimeError(
            "Không tìm thấy template đang hiển thị '+... người khác'."
        )

    candidates.sort(key=lambda item: (-item[0], str(item[1])))

    best_score = candidates[0][0]
    best = [p for s, p in candidates if s == best_score]

    if len(best) != 1:
        details = "\n".join(f" - {p}" for p in best)
        raise RuntimeError(
            "Có nhiều template cùng mức phù hợp; dừng để tránh sửa nhầm:\n"
            + details
        )

    return best[0]


def backup_file(path: Path) -> None:
    dst = BACKUP / path.relative_to(PROJECT)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dst)


def restore_file(path: Path) -> None:
    src = BACKUP / path.relative_to(PROJECT)
    if src.exists():
        shutil.copy2(src, path)


def find_occurrence(text: str) -> int:
    m = re.search(r"người\s+khác", text, flags=re.IGNORECASE)
    if not m:
        raise RuntimeError("Không còn tìm thấy cụm 'người khác'.")
    return m.start()


def remove_slice_limit(text: str, pos: int) -> tuple[str, bool]:
    # Ưu tiên giới hạn [:2] gần cụm "+N người khác".
    left = max(0, pos - 2500)
    window = text[left:pos]

    matches = list(re.finditer(r"\[\s*:\s*2\s*\]", window))
    if matches:
        m = matches[-1]
        start = left + m.start()
        end = left + m.end()
        return text[:start] + text[end:], True

    # Một số template dùng |slice(2) / batch(2) không đúng mục đích;
    # không tự đoán nếu không có [:2].
    return text, False


def hide_extra_count_block(text: str) -> tuple[str, bool]:
    pos = find_occurrence(text)

    # Tìm khối if gần nhất bao quanh dòng "+N người khác".
    start_if = text.rfind("{% if", max(0, pos - 1600), pos)
    end_if = text.find("{% endif %}", pos, min(len(text), pos + 1600))

    if start_if >= 0 and end_if >= 0:
        end_if += len("{% endif %}")
        block = text[start_if:end_if]

        # Chỉ bỏ khi chính khối này chứa cụm "người khác" và không có
        # một if lồng khác để tránh phá cấu trúc.
        if (
            re.search(r"người\s+khác", block, flags=re.IGNORECASE)
            and block.count("{% if") == 1
            and block.count("{% endif %}") == 1
        ):
            replacement = (
                MARK_START
                + "\n"
                + "{# Đã hiển thị đầy đủ toàn bộ thành viên tổ điều tra; "
                  "không rút gọn +N người khác. #}"
                + "\n"
                + MARK_END
            )
            return text[:start_if] + replacement + text[end_if:], True

    # Fallback: bỏ riêng phần tử HTML có chứa "người khác".
    patterns = [
        r"<small\b[^>]*>.*?người\s+khác.*?</small>",
        r"<span\b[^>]*>.*?người\s+khác.*?</span>",
        r"<div\b[^>]*>.*?người\s+khác.*?</div>",
        r"<p\b[^>]*>.*?người\s+khác.*?</p>",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            replacement = (
                MARK_START
                + "\n"
                + "{# Đã bỏ dòng rút gọn +N người khác. #}"
                + "\n"
                + MARK_END
            )
            return text[:m.start()] + replacement + text[m.end():], True

    return text, False


def patch(text: str) -> str:
    if MARK_START in text:
        print(" - Bài 13B-11.10 đã có sẵn, không sửa lặp.")
        return text

    pos = find_occurrence(text)
    text, slice_changed = remove_slice_limit(text, pos)

    text, count_hidden = hide_extra_count_block(text)

    if not slice_changed:
        raise RuntimeError(
            "Đã tìm thấy '+N người khác' nhưng không tìm thấy giới hạn [:2] "
            "gần danh sách thành viên. Dừng để tránh sửa sai."
        )

    if not count_hidden:
        raise RuntimeError(
            "Không xác định an toàn được khối '+N người khác' để ẩn."
        )

    return text


def verify(text: str) -> None:
    if MARK_START not in text or MARK_END not in text:
        raise RuntimeError("Thiếu marker Bài 13B-11.10.")

    if re.search(r"người\s+khác", text, flags=re.IGNORECASE):
        # Cho phép cụm này chỉ xuất hiện trong comment marker của bài.
        cleaned = re.sub(
            re.escape(MARK_START) + r".*?" + re.escape(MARK_END),
            "",
            text,
            flags=re.DOTALL,
        )
        if re.search(r"người\s+khác", cleaned, flags=re.IGNORECASE):
            raise RuntimeError(
                "Template vẫn còn dòng rút gọn '+N người khác'."
            )

    try:
        from jinja2 import Environment
        Environment().parse(text)
    except Exception as exc:
        raise RuntimeError(f"Jinja parse không đạt: {exc}") from exc


def main() -> int:
    print("=" * 110)
    print("BÀI 13B-11.10 - HIỂN THỊ ĐỦ 3 THÀNH VIÊN TỔ ĐIỀU TRA")
    print("=" * 110)
    print()
    print("NGHIỆP VỤ CHỐT:")
    print(" - Mỗi hộ/phiếu thuộc chung tổ điều tra 3 người.")
    print(" - Cột Người điều tra hiển thị đủ cả 3 thành viên.")
    print(" - Không còn '+1 người khác'.")
    print(" - Một thành viên hoàn thành phiếu = phiếu hoàn thành cho cả tổ.")
    print(" - Không yêu cầu cả 3 người cùng nhập/hoàn thành.")
    print()
    print("BẢN CÀI NÀY:")
    print(" - Chỉ sửa template hiển thị danh sách hộ.")
    print(" - Không sửa database.")
    print(" - Không đổi phân công.")
    print(" - Không đổi người chính/phụ.")
    print(" - Không tạo trạng thái hoàn thành riêng từng giáo viên.")
    print()

    target = find_target()
    print("Template được xác định:", target)

    BACKUP.mkdir(parents=True, exist_ok=False)
    backup_file(target)
    print("Backup source:", BACKUP)

    try:
        before = read_text(target)
        after = patch(before)
        verify(after)
        write_text(target, after)

        print()
        print("KIỂM TRA SAU CÀI:")
        print(" - Bỏ giới hạn chỉ hiện 2 người: OK")
        print(" - Ẩn '+N người khác': OK")
        print(" - Hiển thị toàn bộ thành viên được phân công: OK")
        print(" - Jinja parse: OK")
        print(" - Database: KHÔNG THAY ĐỔI")
        print()
        print("CÀI ĐẶT BÀI 13B-11.10 THÀNH CÔNG")
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
