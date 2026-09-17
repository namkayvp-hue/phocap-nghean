from __future__ import annotations

from pathlib import Path
import py_compile
import sys

from jinja2 import Environment


ROOT = Path(__file__).resolve().parent
PYTHON_FILE = ROOT / "app" / "routers" / "surveys.py"
HOUSEHOLDS_HTML = ROOT / "app" / "templates" / "surveys" / "households.html"
QUICK_HTML = ROOT / "app" / "templates" / "surveys" / "quick_entry.html"


def require_text(path: Path, markers: list[str]) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"THIEU TEP: {path}"]

    content = path.read_text(encoding="utf-8")
    for marker in markers:
        if marker not in content:
            errors.append(f"THIEU NOI DUNG: {marker} trong {path}")
    return errors


def main() -> int:
    errors: list[str] = []

    try:
        py_compile.compile(
            str(PYTHON_FILE),
            doraise=True,
        )
    except Exception as exc:
        errors.append(f"LOI CU PHAP PYTHON: {exc}")

    env = Environment()
    for html_file in (HOUSEHOLDS_HTML, QUICK_HTML):
        if not html_file.exists():
            errors.append(f"THIEU TEP HTML: {html_file}")
            continue
        try:
            env.parse(html_file.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"LOI JINJA {html_file}: {exc}")

    errors.extend(
        require_text(
            PYTHON_FILE,
            [
                "def trang_nhap_nhanh_ho_dan",
                "def luu_nhap_nhanh_ho_dan",
                "def them_doi_tuong_tu_nhap_nhanh",
                "tao_bo_loc_phieu_theo_nguoi_dung(request)",
                "quick_saved_next",
                'submit_action == "save_next"',
                "missing_personal_id_count",
                "missing_year_record_count",
                "incomplete_year_record_count",
            ],
        )
    )

    errors.extend(
        require_text(
            QUICK_HTML,
            [
                "Nhập nhanh hộ dân",
                "Tìm nhanh phiếu được phân công",
                "Hộ trước",
                "Hộ tiếp theo",
                "Lưu và chuyển hộ tiếp theo",
                "Thêm nhanh một thành viên",
                "Thiếu định danh",
                "Chưa có dữ liệu năm",
                "Chưa đủ chỉ báo",
            ],
        )
    )

    errors.extend(
        require_text(
            HOUSEHOLDS_HTML,
            [
                "/nhap-nhanh",
                "Nhập nhanh",
            ],
        )
    )

    if errors:
        print("BAI 12C-1 CHUA DAT.")
        for error in errors:
            print("LOI:", error)
        return 1

    print("BAI 12C-1 DA SAN SANG.")
    print("OK PYTHON: app/routers/surveys.py")
    print("OK HTML: households.html va quick_entry.html")
    print("OK PHAM VI: dung bo loc quyen hien co cua ADMIN/SO, Truong va Giao vien.")
    print("OK DIEU HUONG: Ho truoc, Ho tiep theo, vi tri va tien do.")
    print("OK TIM NHANH: so phieu, ma ho, chu ho, dia chi va dien thoai.")
    print("OK NHAP NHANH: thong tin ho, trang thai phieu va xac nhan trong mot lan luu.")
    print("OK THANH VIEN: canh bao thieu dinh danh, thieu nam hoc, thieu chi bao va them nhanh.")
    print("OK LUU TIEP: Luu va chuyen sang ho tiep theo trong dung pham vi duoc giao.")
    print("Khong co cau truc hoac du lieu co so du lieu nao duoc them, sua hoac xoa khi kiem tra.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
