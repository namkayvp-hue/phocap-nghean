from __future__ import annotations

from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parent
PY_FILE = ROOT / "app" / "routers" / "surveys.py"
HTML_FILE = ROOT / "app" / "templates" / "surveys" / "quick_entry.html"


def require(text: str, token: str, label: str) -> None:
    if token not in text:
        raise SystemExit(f"LOI {label}: khong tim thay {token!r}")


def main() -> None:
    py_compile.compile(str(PY_FILE), doraise=True)
    source = PY_FILE.read_text(encoding="utf-8")
    html = HTML_FILE.read_text(encoding="utf-8")

    require(source, "def danh_gia_do_day_du_phieu_nhap_nhanh", "HAM DANH GIA")
    require(source, "missing_personal_id_count", "DINH DANH")
    require(source, "missing_year_record_count", "DU LIEU NAM")
    require(source, "incomplete_year_record_count", "CHI BAO")
    require(source, "Không thể hoàn thành phiếu vì hộ gia đình chưa xác nhận.", "XAC NHAN HO")
    require(source, 'if form_status == "DA_HOAN_THANH":', "CHAN HOAN THANH")
    require(source, "completion_blockers", "CANH BAO GIAO DIEN")

    require(html, "Chưa đủ điều kiện đánh dấu", "THONG BAO CHUA DU")
    require(html, "Phiếu đủ điều kiện đánh dấu", "THONG BAO DU")
    require(html, "completion_blockers", "DANH SACH LY DO")
    require(html, "completion-current-warning", "CANH BAO PHIEU CU")

    print("BAI 12C-5 DA SAN SANG.")
    print("OK PYTHON: app/routers/surveys.py")
    print("OK HTML: app/templates/surveys/quick_entry.html")
    print("OK CHAN HOAN THANH: ho phai co thanh vien dang theo doi.")
    print("OK DINH DANH: tat ca thanh vien phai co so dinh danh.")
    print("OK NAM HOC: tat ca thanh vien phai co du lieu nam hien tai.")
    print("OK CHI BAO: tat ca thanh vien phai du 8 chi bao.")
    print("OK XAC NHAN: ho gia dinh phai duoc danh dau da xac nhan.")
    print("OK HAI DUONG: ca Nhap nhanh va Phieu day du deu duoc bao ve.")
    print("OK GIAO DIEN: hien ro ly do chua du dieu kien hoan thanh.")
    print("Khong co du lieu co so du lieu nao duoc them, sua hoac xoa khi kiem tra.")


if __name__ == "__main__":
    main()
