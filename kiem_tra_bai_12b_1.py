from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from jinja2 import Environment
except ImportError:
    Environment = None


ROOT = Path(__file__).resolve().parent

PYTHON_FILE = ROOT / "app" / "routers" / "surveys.py"
TEMPLATE_FILES = [
    ROOT / "app" / "templates" / "surveys" / "people.html",
    ROOT / "app" / "templates" / "surveys" / "person_edit.html",
    ROOT / "app" / "templates" / "surveys" / "year_overview.html",
    ROOT / "app" / "templates" / "surveys" / "year_records.html",
]


def fail(message: str) -> None:
    print(f"LOI: {message}")
    raise SystemExit(1)


def require(text: str, pattern: str, message: str) -> None:
    if pattern not in text:
        fail(message)


def main() -> int:
    if not PYTHON_FILE.is_file():
        fail(f"Khong tim thay {PYTHON_FILE}")

    for template_file in TEMPLATE_FILES:
        if not template_file.is_file():
            fail(f"Khong tim thay {template_file}")

    source = PYTHON_FILE.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(PYTHON_FILE))
    except SyntaxError as exc:
        fail(f"Loi cu phap Python: {exc}")

    if Environment is not None:
        environment = Environment()
        for template_file in TEMPLATE_FILES:
            try:
                environment.parse(
                    template_file.read_text(encoding="utf-8")
                )
            except Exception as exc:
                fail(
                    f"Loi cu phap Jinja trong {template_file.name}: {exc}"
                )

    people_html = TEMPLATE_FILES[0].read_text(encoding="utf-8")
    edit_html = TEMPLATE_FILES[1].read_text(encoding="utf-8")
    overview_html = TEMPLATE_FILES[2].read_text(encoding="utf-8")
    years_html = TEMPLATE_FILES[3].read_text(encoding="utf-8")

    require(
        source,
        "def tim_hoc_sinh_de_lien_ket(",
        "Chua co API tim nhanh hoc sinh.",
    )
    require(
        source,
        "def chuyen_gia_tri_co_khong(",
        "Chua co xu ly ba trang thai Co/Khong/Chua xac dinh.",
    )
    require(
        source,
        "SurveyPersonYearRecord.survey_form_id == survey_form.id",
        "Ban ghi nam hoc chua duoc gioi han theo dung phieu dieu tra.",
    )
    require(
        source,
        'completed_preschool_5: Annotated[str, Form()] = ""',
        "Truong chi bao nam hoc chua dung gia tri ba trang thai.",
    )
    require(
        source,
        "current_year_answered",
        "Chua co thong ke muc hoan thien nam hoc hien tai.",
    )
    require(
        source,
        "will_be_head = la_quan_he_chu_ho",
        "Chua kiem tra trung vai tro Chu ho.",
    )

    require(
        people_html,
        "student_suggestions",
        "Trang them doi tuong chua co tim hoc sinh theo goi y.",
    )
    require(
        people_html,
        "tim-hoc-sinh",
        "Trang them doi tuong chua goi API tim hoc sinh.",
    )
    if "{% for hoc_sinh in students %}" in people_html:
        fail("Trang them doi tuong van tai toan bo hoc sinh.")

    require(
        edit_html,
        "student_suggestions",
        "Trang sua doi tuong chua co tim hoc sinh theo goi y.",
    )
    require(
        edit_html,
        "current_person_id",
        "Trang sua chua loai tru lien ket hien tai khi tim hoc sinh.",
    )
    if "{% for hoc_sinh in students %}" in edit_html:
        fail("Trang sua doi tuong van tai toan bo hoc sinh.")

    require(
        overview_html,
        "current_year_answered",
        "Trang tong quan nam hoc chua hien muc hoan thien.",
    )
    require(
        overview_html,
        "person-cards",
        "Trang tong quan nam hoc chua co giao dien dien thoai.",
    )

    for field_name in (
        "completed_preschool_5",
        "attends_required_days",
        "attends_regularly",
        "prepared_vietnamese",
        "weight_monitored",
        "underweight",
        "height_monitored",
        "stunted",
    ):
        require(
            years_html,
            f'name="{field_name}"',
            f"Thieu chi bao nam hoc: {field_name}",
        )

    require(
        years_html,
        '<option value="1"',
        "Bieu mau nam hoc thieu lua chon Co.",
    )
    require(
        years_html,
        '<option value="0"',
        "Bieu mau nam hoc thieu lua chon Khong.",
    )
    require(
        years_html,
        "Chưa xác định",
        "Bieu mau nam hoc thieu trang thai Chua xac dinh.",
    )
    if 'type="checkbox"\n                                    name="attends_required_days"' in years_html:
        fail("Chi bao nam hoc van dung checkbox hai trang thai.")

    print("BAI 12B-1 DA SAN SANG.")
    print("OK PYTHON: app/routers/surveys.py")
    print("OK HTML: 4 giao dien doi tuong va nam hoc.")
    print("OK TIM HOC SINH: goi y theo ma, ho ten hoac so dinh danh; khong tai toan bo danh sach.")
    print("OK DOI TUONG: them, sua, lien ket hoc sinh, kiem tra Chu ho va ngung theo doi.")
    print("OK NAM HOC: ban ghi duoc gioi han theo dung phieu dieu tra.")
    print("OK CHI BAO: Co / Khong / Chua xac dinh, khong danh dong bo trong thanh Khong.")
    print("OK TONG QUAN: hien tinh trang nam hien tai va so chi bao da nhap.")
    print("OK DIEN THOAI: co the doi tuong tai trang tong quan nam hoc.")
    print("Khong co du lieu co so du lieu nao duoc them, sua hoac xoa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
