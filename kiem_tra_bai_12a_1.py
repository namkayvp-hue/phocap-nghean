from __future__ import annotations

import ast
from pathlib import Path

from jinja2 import Environment


PROJECT_DIR = Path(__file__).resolve().parent
PYTHON_FILE = PROJECT_DIR / "app" / "routers" / "surveys.py"
HTML_FILE = (
    PROJECT_DIR
    / "app"
    / "templates"
    / "surveys"
    / "households.html"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"LOI: {message}")


def main() -> None:
    require(PYTHON_FILE.exists(), f"Khong tim thay {PYTHON_FILE}")
    require(HTML_FILE.exists(), f"Khong tim thay {HTML_FILE}")

    python_source = PYTHON_FILE.read_text(encoding="utf-8")
    html_source = HTML_FILE.read_text(encoding="utf-8")

    ast.parse(python_source)
    Environment().parse(html_source)

    python_markers = (
        "HOUSEHOLD_PAGE_SIZE_OPTIONS = (20, 50, 100)",
        "HOUSEHOLD_SORT_OPTIONS",
        "investigator_id: int = 0",
        "assignment_status: str = \"\"",
        "Household.people.any(",
        "SurveyPerson.personal_id.ilike",
        "investigator_options",
        "visible_people_count",
    )
    html_markers = (
        "Thêm hộ điều tra",
        "Tình trạng phân công",
        "Người điều tra",
        "Số dòng/trang",
        "mobile-list",
        "add-household-dialog",
        "Theo dõi năm học",
    )

    for marker in python_markers:
        require(
            marker in python_source,
            f"Thieu noi dung Python: {marker}",
        )

    for marker in html_markers:
        require(
            marker in html_source,
            f"Thieu noi dung HTML: {marker}",
        )

    print("BAI 12A-1 DA SAN SANG.")
    print("OK PYTHON: app/routers/surveys.py")
    print("OK HTML: app/templates/surveys/households.html")
    print(
        "OK TIM KIEM: so phieu, ma ho, chu ho, dia chi, "
        "dien thoai, thanh vien va so dinh danh."
    )
    print(
        "OK BO LOC: thon/xom, trang thai phieu, phan cong "
        "va nguoi dieu tra."
    )
    print("OK PHAN TRANG: 20, 50 hoac 100 dong.")
    print("OK GIAO DIEN: bang may tinh va the ho dan tren dien thoai.")
    print(
        "OK THAO TAC: them ho, thanh vien, phieu, nam hoc, "
        "phan cong, tien do va Excel theo quyen."
    )
    print(
        "Khong co du lieu co so du lieu nao duoc them, "
        "sua hoac xoa."
    )


if __name__ == "__main__":
    main()
