from __future__ import annotations

from pathlib import Path
from datetime import datetime
import shutil
import sys

VERSION = "BAI_13B_12_V2_4_4_2"
MARKER = "BAI_13B_12_V2_4_4_2_CONCLUSION_PRIORITY"


def find_project_root() -> Path:
    candidates = [Path(r"C:\PhoCap"), Path.cwd()]
    for root in candidates:
        if (root / "app" / "pcgd_xmc_report_builders_v1.py").exists():
            return root
    raise FileNotFoundError(
        "Khong tim thay du an. Can co tep app\\pcgd_xmc_report_builders_v1.py trong C:\\PhoCap."
    )


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Khong the ap dung ban va [{label}]: tim thay {count} vi tri, can dung 1 vi tri.")
    return text.replace(old, new, 1)


def main() -> int:
    print(VERSION)
    print("- XMC-4: ket luan dung chinh ty le dang tong hop tren bieu.")
    print("- TH/THCS: khong de 'Chua du DK' ghi de mot ket qua 'Khong dat' da xac dinh.")
    print("- Giu nguyen database, mau Excel, menu, giao dien va luong dien thoai.\n")

    root = find_project_root()
    target = root / "app" / "pcgd_xmc_report_builders_v1.py"
    original = target.read_text(encoding="utf-8")

    if MARKER in original:
        print("[OK] Ban va V2.4.4.2 da co san trong ma nguon. Khong can cai lai.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "backups" / f"backup_bai_13b_12_v2_4_4_2_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_file = backup_dir / "pcgd_xmc_report_builders_v1.py"
    shutil.copy2(target, backup_file)
    print(f"[BACKUP] {backup_file}")

    try:
        text = original

        old_rate = '''        positive = _xmc1471b_sum(metrics, ages, true_key)\n        negative = _xmc1471b_sum(metrics, ages, false_key)\n\n        if int(positive or 0) + int(negative or 0) != int(population):\n            return None\n\n        return _percent(positive, population)\n'''
        new_rate = '''        positive = _xmc1471b_sum(metrics, ages, true_key)\n\n        # BAI 13B-12 V2.4.4.2:\n        # Dong bo ket luan voi chinh ty le dang hien tren XMC-4.\n        # Nguoi chua duoc xac nhan dat muc biet chu khong duoc tinh vao tu so,\n        # nhung van nam trong tong dan so cua nhom tuoi (mau so).\n        # Vi vay khong bien du lieu chua xac nhan thanh "thieu du lieu" neu\n        # bieu da tinh duoc ty le tu tong so va so nguoi duoc cong nhan.\n        return _percent(positive, population)\n'''
        text = replace_once(text, old_rate, new_rate, "XMC visible-rate conclusion")

        old_th = '''        if selected_school_id is not None:\n            ws["T8"] = None\n        elif not state["all_passed"]:\n            if (\n                state["staff_status"] == "Chưa đạt"\n                or state["csvc_status"] == "Chưa đạt"\n            ):\n                ws["T8"] = "Chưa đạt ĐK"\n            else:\n                ws["T8"] = "Chưa đủ ĐK"\n        return\n'''
        new_th = '''        if selected_school_id is not None:\n            ws["T8"] = None\n        elif not state["all_passed"]:\n            # BAI 13B-12 V2.4.4.2:\n            # Neu ket qua chi tieu da xac dinh chac chan "Khong dat" thi\n            # khong de trang thai dieu kien bao dam ghi de ket luan do.\n            # Chi dung "Chua du/Chua dat DK" khi ban than chi tieu chua fail.\n            existing_conclusion = str(ws["T8"].value or "").strip().casefold()\n            if existing_conclusion == "không đạt".casefold():\n                return\n            if (\n                state["staff_status"] == "Chưa đạt"\n                or state["csvc_status"] == "Chưa đạt"\n            ):\n                ws["T8"] = "Chưa đạt ĐK"\n            else:\n                ws["T8"] = "Chưa đủ ĐK"\n        return\n'''
        text = replace_once(text, old_th, new_th, "TH conclusion priority")

        old_thcs = '''        if selected_school_id is not None:\n            ws[conclusion_ref] = None\n        elif not state["all_passed"]:\n            if (\n                state["staff_status"] == "Chưa đạt"\n                or state["csvc_status"] == "Chưa đạt"\n            ):\n                ws[conclusion_ref] = "Chưa đạt ĐK"\n            else:\n                ws[conclusion_ref] = "Chưa đủ ĐK"\n'''
        new_thcs = '''        if selected_school_id is not None:\n            ws[conclusion_ref] = None\n        elif not state["all_passed"]:\n            # BAI 13B-12 V2.4.4.2:\n            # Uu tien mot ket qua "Khong dat" da duoc xac dinh tu cac\n            # tieu chi/đieu kien tien quyet; khong ghi de bang "Chua du DK".\n            existing_conclusion = str(ws[conclusion_ref].value or "").strip().casefold()\n            if existing_conclusion == "không đạt".casefold():\n                return\n            if (\n                state["staff_status"] == "Chưa đạt"\n                or state["csvc_status"] == "Chưa đạt"\n            ):\n                ws[conclusion_ref] = "Chưa đạt ĐK"\n            else:\n                ws[conclusion_ref] = "Chưa đủ ĐK"\n'''
        text = replace_once(text, old_thcs, new_thcs, "THCS conclusion priority")

        text += f"\n# {MARKER}\n"

        # Kiem tra cu phap truoc khi ghi de file dang chay.
        compile(text, str(target), "exec")
        target.write_text(text, encoding="utf-8")

        # Kiem tra lai file vua ghi.
        compile(target.read_text(encoding="utf-8"), str(target), "exec")

        print("[OK] Da sua app\\pcgd_xmc_report_builders_v1.py")
        print("[OK] Kiem tra cu phap Python: DAT")
        print("\n=== CAI DAT THANH CONG ===")
        print(f"Ban sao an toan: {backup_dir}")
        print("Database phocap.db khong bi thay doi.")
        print("Khoi dong lai Uvicorn va xuat lai XMC-4, THCS-M2, TH-02 cap Xa.")
        return 0

    except Exception as exc:
        print(f"[LOI] {type(exc).__name__}: {exc}")
        print("Dang khoi phuc tep da sao luu...")
        try:
            shutil.copy2(backup_file, target)
            print(f"[KHOI PHUC] {target}")
            print("Du an da duoc dua ve trang thai truoc khi cai dat.")
        except Exception as restore_exc:
            print(f"[CANH BAO] Khong khoi phuc tu dong duoc: {restore_exc}")
            print(f"Ban backup van nam tai: {backup_file}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
