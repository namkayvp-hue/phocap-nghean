from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT = Path(r"C:\PhoCap")
SURVEYS = PROJECT / "app" / "routers" / "surveys.py"

TARGET_NAMES = [
    "trang_giao_phieu_cho_giao_vien",
    "luu_giao_phieu_cho_giao_vien",
    "luu_phan_cong_v4_theo_cap",
]

KEYWORD_HINTS = [
    "assignment_level",
    "bulk_assignments.html",
    "phan-cong-truong/gui-xa",
    "survey_school_assignments",
    "survey_assignment_logs",
]

def section(title: str) -> None:
    print()
    print("=" * 120)
    print(title)
    print("=" * 120)

def get_source_segment(text: str, node: ast.AST) -> str:
    lines = text.splitlines()
    start = getattr(node, "lineno", 1) - 1
    # Include decorators
    decos = getattr(node, "decorator_list", [])
    if decos:
        start = min(getattr(d, "lineno", start + 1) for d in decos) - 1
    end = getattr(node, "end_lineno", start + 1)
    return "\n".join(f"{i+1:5}: {lines[i]}" for i in range(start, min(end, len(lines))))

def main() -> None:
    print("KIỂM TRA BÀI 13B-10 V3.12A - SOURCE CHÍNH XÁC TRANG GIAO PHIẾU")
    print("CHỈ ĐỌC - KHÔNG SỬA SOURCE / DATABASE")
    print("File:", SURVEYS)

    if not SURVEYS.exists():
        raise RuntimeError(f"Không tìm thấy {SURVEYS}")

    text = SURVEYS.read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(text)

    funcs = {
        n.name: n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    section("1. HÀM GET trang_giao_phieu_cho_giao_vien")
    node = funcs.get("trang_giao_phieu_cho_giao_vien")
    if node:
        print(get_source_segment(text, node))
    else:
        print("Không tìm thấy.")

    section("2. HÀM POST luu_giao_phieu_cho_giao_vien")
    node = funcs.get("luu_giao_phieu_cho_giao_vien")
    if node:
        print(get_source_segment(text, node))
    else:
        print("Không tìm thấy.")

    section("3. HÀM CHUNG luu_phan_cong_v4_theo_cap")
    node = funcs.get("luu_phan_cong_v4_theo_cap")
    if node:
        print(get_source_segment(text, node))
    else:
        print("Không tìm thấy.")

    section("4. CÁC HÀM THAM CHIẾU bulk_assignments.html / assignment_level")
    for name, node in sorted(funcs.items(), key=lambda kv: getattr(kv[1], "lineno", 0)):
        seg = ast.get_source_segment(text, node) or ""
        if "bulk_assignments.html" in seg or (
            "assignment_level" in seg and
            any(k in seg for k in ("SurveyForm", "form_ids", "visible_forms", "assignment"))
        ):
            print(f"\n### FUNCTION: {name} ###")
            print(get_source_segment(text, node))

    section("5. ROUTE /phan-cong-truong/gui-xa")
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if "phan-cong-truong/gui-xa" in line]
    if not hits:
        print("Không tìm thấy route.")
    else:
        for hit in hits:
            # Find nearest function node spanning this line
            line_no = hit + 1
            candidates = []
            for name, node in funcs.items():
                start = getattr(node, "lineno", 0)
                end = getattr(node, "end_lineno", 0)
                deco_start = min([getattr(d, "lineno", start) for d in getattr(node, "decorator_list", [])] or [start])
                if deco_start <= line_no <= end:
                    candidates.append((name, node))
            if candidates:
                name, node = min(candidates, key=lambda x: getattr(x[1], "end_lineno", 10**9)-getattr(x[1], "lineno", 0))
                print(f"\n### FUNCTION: {name} ###")
                print(get_source_segment(text, node))
            else:
                start = max(0, hit-5)
                end = min(len(lines), hit+30)
                for i in range(start, end):
                    print(f"{i+1:5}: {lines[i]}")

    section("6. HÀM CÓ survey_assignment_logs / SurveyAssignmentLog")
    for name, node in sorted(funcs.items(), key=lambda kv: getattr(kv[1], "lineno", 0)):
        seg = ast.get_source_segment(text, node) or ""
        if "survey_assignment_logs" in seg or "SurveyAssignmentLog" in seg:
            print(f"\n### FUNCTION: {name} ###")
            print(get_source_segment(text, node))

    section("7. HÀM CÓ survey_school_assignments / SurveySchoolAssignment")
    for name, node in sorted(funcs.items(), key=lambda kv: getattr(kv[1], "lineno", 0)):
        seg = ast.get_source_segment(text, node) or ""
        if "survey_school_assignments" in seg or "SurveySchoolAssignment" in seg:
            print(f"\n### FUNCTION: {name} ###")
            print(get_source_segment(text, node))

    section("8. KẾT LUẬN")
    print("Đã in đúng các function body cần để làm V3.12 chính thức.")
    print("KHÔNG INSERT / UPDATE / DELETE.")
    print("Gửi toàn bộ mục 1, 3, 4 và 5 cho ChatGPT.")

if __name__ == "__main__":
    main()
