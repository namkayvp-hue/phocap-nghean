from __future__ import annotations

import argparse
import hashlib
import py_compile
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


EXPECTED_SHA256 = "f30f2ad9a5abb6b4cb19c145f0c65e458d5f259979219c067e90eb9facbf6666"

MARKER_COMMUNE = "CHOT_DIEU_KIEN_KHOA_XA_100_PHAN_TRAM_V2"
MARKER_PROVINCE = "CHOT_DIEU_KIEN_KHOA_TINH_TAT_CA_XA_DA_KHOA_V2"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def find_root(arg_root: str | None) -> Path:
    candidates = []
    if arg_root:
        candidates.append(Path(arg_root))
    candidates.extend([Path.cwd(), Path(r"C:\PhoCap")])

    for p in candidates:
        try:
            p = p.resolve()
        except Exception:
            continue
        if (p / "app" / "routers" / "survey_school_workflow.py").is_file():
            return p

    raise SystemExit(
        "KHÔNG TÌM THẤY dự án. Hãy chép file cài đặt vào C:\\PhoCap "
        "và chạy PowerShell tại C:\\PhoCap."
    )


def db_integrity(db_path: Path) -> tuple[str, int]:
    if not db_path.is_file():
        return "không có database", 0
    uri = f"file:{db_path.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        fk_count = len(list(conn.execute("PRAGMA foreign_key_check")))
        return integrity, fk_count
    finally:
        conn.close()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Không thể cài an toàn phần '{label}': "
            f"cần đúng 1 vị trí, nhưng tìm thấy {count}."
        )
    return text.replace(old, new, 1)


def replace_between(
    text: str,
    start_marker: str,
    end_marker: str,
    replacement: str,
    label: str,
) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"Không tìm thấy điểm bắt đầu của '{label}'.")
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        raise RuntimeError(f"Không tìm thấy điểm kết thúc của '{label}'.")
    return text[:start] + replacement.rstrip() + "\n\n\n" + text[end:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default=None,
        help="Chỉ dùng khi cần kiểm thử; mặc định tự tìm C:\\PhoCap.",
    )
    args = parser.parse_args()

    root = find_root(args.root)
    router_path = root / "app" / "routers" / "survey_school_workflow.py"
    db_path = root / "data" / "phocap.db"

    print("=" * 100)
    print("CÀI ĐẶT KHÓA 3 CẤP V2")
    print("Khóa trường 100% -> Khóa xã khi toàn xã hoàn tất -> Khóa Sở khi tất cả xã đã khóa")
    print("=" * 100)
    print(f"Dự án   : {root}")
    print(f"Mã nguồn: {router_path}")
    print(f"Database : {db_path}")

    original = router_path.read_text(encoding="utf-8")
    if MARKER_COMMUNE in original and MARKER_PROVINCE in original:
        print("\nBộ cài V2 đã có trong mã nguồn. Không cài lặp.")
        print("Không có thay đổi nào được thực hiện.")
        return 0

    current_hash = sha256(router_path)
    print(f"\nSHA256 hiện tại: {current_hash}")
    if current_hash != EXPECTED_SHA256:
        print("\nDỪNG AN TOÀN.")
        print("Mã nguồn đã khác bản vừa kiểm tra ngày 28/08/2026.")
        print("Không tự động sửa để tránh ghi đè thay đổi mới.")
        print("Hãy gửi lại file survey_school_workflow.py hoặc ZIP mã nguồn mới nhất.")
        return 2

    integrity, fk_count = db_integrity(db_path)
    print(f"Database integrity_check    : {integrity}")
    print(f"Database foreign_key_check  : {fk_count} lỗi")
    if db_path.is_file() and (integrity.lower() != "ok" or fk_count != 0):
        print("\nDỪNG AN TOÀN vì database chưa đạt kiểm tra.")
        return 3

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "exports" / f"backup_truoc_khoa_3_cap_v2_{stamp}"
    backup_router = backup_dir / "app" / "routers" / "survey_school_workflow.py"
    backup_db = backup_dir / "data" / "phocap.db"
    report_path = root / "exports" / f"bao_cao_cai_dat_khoa_3_cap_v2_{stamp}.txt"

    backup_router.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(router_path, backup_router)

    if db_path.is_file():
        backup_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, backup_db)

    print(f"\nĐã backup mã nguồn: {backup_router}")
    if db_path.is_file():
        print(f"Đã backup database: {backup_db}")

    new_text = original

    old_messages = '''    "commune_locked": "Đã khóa toàn bộ dữ liệu điều tra của xã/phường.",
    "commune_unlocked": "Đã mở lại dữ liệu điều tra của xã/phường.",
    "province_locked": "Đã khóa đợt điều tra trên toàn tỉnh.",
'''
    new_messages = '''    "commune_not_complete": (
        "Chưa thể khóa toàn xã: phải hoàn thành 100% phiếu điều tra của địa bàn."
    ),
    "commune_schools_not_locked": (
        "Chưa thể khóa toàn xã: tất cả trường có phiếu phải được khóa/xác nhận hoàn thành trước."
    ),
    "commune_locked": "Đã khóa toàn bộ dữ liệu điều tra của xã/phường.",
    "commune_unlocked": "Đã mở lại dữ liệu điều tra của xã/phường.",
    "province_not_ready": (
        "Chưa thể khóa toàn tỉnh: tất cả xã/phường của năm học phải khóa cấp xã trước."
    ),
    "province_no_batches": "Năm học chưa có đợt điều tra để khóa.",
    "province_locked": "Đã khóa đợt điều tra trên toàn tỉnh.",
'''
    new_text = replace_once(
        new_text,
        old_messages,
        new_messages,
        "bổ sung thông báo điều kiện khóa",
    )

    commune_function = r'''@router.post("/{batch_id}/khoa-xa")
def khoa_toan_xa(
    request: Request,
    batch_id: int,
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    batch = lay_dot(db, batch_id)
    reason = str(reason or "").strip()
    if not reason:
        return redirect_workflow(batch_id, "invalid_reason")
    if batch is None or not co_quyen_quan_ly_xa(user=actor, batch=batch):
        return redirect_workflow(batch_id, "forbidden")

    state = lay_trang_thai_dia_ban(db, batch)
    if state.is_province_locked:
        return redirect_workflow(batch.id, "province_lock_blocks")

    # === CHOT_DIEU_KIEN_KHOA_XA_100_PHAN_TRAM_V2 ===
    # Cấp xã chỉ được khóa khi:
    # 1) toàn bộ phiếu của địa bàn đã hoàn thành;
    # 2) mọi trường thực sự có phiếu đều đã được xã khóa/xác nhận hoàn thành.
    totals = db.execute(
        select(
            func.count(SurveyForm.id),
            func.sum(
                case(
                    (SurveyForm.status == "DA_HOAN_THANH", 1),
                    else_=0,
                )
            ),
        ).where(SurveyForm.survey_batch_id == batch.id)
    ).one()

    form_total = int(totals[0] or 0)
    completed_form_total = int(totals[1] or 0)

    if form_total <= 0 or completed_form_total != form_total:
        return redirect_workflow(batch.id, "commune_not_complete")

    assignments = list(
        db.scalars(
            select(SurveySchoolAssignment).where(
                SurveySchoolAssignment.survey_batch_id == batch.id
            )
        ).all()
    )

    for assignment in assignments:
        counts = dem_phieu_cua_truong(
            db,
            batch_id=batch.id,
            school_id=int(assignment.school_id),
        )
        school_form_total = int(counts.get("form_total") or 0)

        # Nhiệm vụ chưa có phiếu không cản khóa toàn xã.
        # Có thể thu hồi nhiệm vụ này riêng trên màn hình phân công trường.
        if school_form_total <= 0:
            continue

        if (
            not bool(assignment.is_locked)
            or str(assignment.status or "") != "DA_HOAN_THANH"
        ):
            return redirect_workflow(
                batch.id,
                "commune_schools_not_locked",
            )
    # === CHOT_DIEU_KIEN_KHOA_XA_100_PHAN_TRAM_V2_END ===

    state.is_commune_locked = True
    state.commune_locked_at = datetime.now()
    state.commune_locked_by_user_id = actor.get("id")
    state.commune_lock_reason = reason
    dong_bo_khoa_dot(batch=batch, state=state, actor=actor, reason=reason)

    ghi_nhat_ky(
        db=db,
        batch_id=batch.id,
        school_id=None,
        action="KHOA_XA",
        actor=actor,
        reason=reason,
        form_total=form_total,
        completed_form_total=completed_form_total,
    )
    db.commit()
    return redirect_workflow(batch.id, "commune_locked")'''

    new_text = replace_between(
        new_text,
        '@router.post("/{batch_id}/khoa-xa")',
        '@router.post("/{batch_id}/mo-khoa-xa")',
        commune_function,
        "khóa toàn xã",
    )

    province_function = r'''@router.post("/dieu-hanh-trien-khai/khoa-toan-tinh")
def khoa_toan_tinh(
    request: Request,
    school_year_id: Annotated[int, Form()],
    reason: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    actor = lay_nguoi_dung(request)
    reason = str(reason or "").strip()
    if not is_admin_role(actor.get("role_code")):
        return RedirectResponse("/?status=forbidden", 303)
    if not reason:
        query = urlencode(
            {"school_year_id": school_year_id, "status": "invalid_reason"}
        )
        return RedirectResponse(
            f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
        )

    batches = list(
        db.scalars(
            select(SurveyBatch).where(
                SurveyBatch.school_year_id == school_year_id
            )
        ).all()
    )

    # === CHOT_DIEU_KIEN_KHOA_TINH_TAT_CA_XA_DA_KHOA_V2 ===
    # Khóa cấp Sở là khóa cuối cùng:
    # chỉ thực hiện khi tất cả xã/phường của năm học đã tự khóa cấp xã.
    if not batches:
        query = urlencode(
            {"school_year_id": school_year_id, "status": "province_no_batches"}
        )
        return RedirectResponse(
            f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
        )

    for batch in batches:
        state = lay_trang_thai_dia_ban(db, batch)
        if not bool(state.is_commune_locked):
            db.rollback()
            query = urlencode(
                {"school_year_id": school_year_id, "status": "province_not_ready"}
            )
            return RedirectResponse(
                f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
            )
    # === CHOT_DIEU_KIEN_KHOA_TINH_TAT_CA_XA_DA_KHOA_V2_END ===

    for batch in batches:
        state = lay_trang_thai_dia_ban(db, batch)
        state.is_province_locked = True
        state.province_locked_at = datetime.now()
        state.province_locked_by_user_id = actor.get("id")
        state.province_lock_reason = reason
        dong_bo_khoa_dot(batch=batch, state=state, actor=actor, reason=reason)
        ghi_nhat_ky(
            db=db,
            batch_id=batch.id,
            school_id=None,
            action="KHOA_TINH",
            actor=actor,
            reason=reason,
        )
    db.commit()
    query = urlencode(
        {"school_year_id": school_year_id, "status": "province_locked"}
    )
    return RedirectResponse(
        f"/dieu-tra/dieu-hanh-trien-khai?{query}", 303
    )'''

    new_text = replace_between(
        new_text,
        '@router.post("/dieu-hanh-trien-khai/khoa-toan-tinh")',
        '@router.post("/dieu-hanh-trien-khai/mo-khoa-toan-tinh")',
        province_function,
        "khóa toàn tỉnh",
    )

    if MARKER_COMMUNE not in new_text or MARKER_PROVINCE not in new_text:
        raise RuntimeError("Không tạo được đủ marker V2; dừng cài đặt.")

    try:
        router_path.write_text(new_text, encoding="utf-8")
        py_compile.compile(str(router_path), doraise=True)
    except Exception as exc:
        shutil.copy2(backup_router, router_path)
        print("\nCÀI ĐẶT LỖI - ĐÃ TỰ KHÔI PHỤC FILE MÃ NGUỒN.")
        print(f"Lỗi: {exc}")
        return 4

    after_hash = sha256(router_path)
    integrity2, fk_count2 = db_integrity(db_path)

    report_lines = [
        "BÁO CÁO CÀI ĐẶT KHÓA 3 CẤP V2",
        f"Thời gian: {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"Dự án: {root}",
        f"File đã sửa: {router_path}",
        f"SHA256 trước: {current_hash}",
        f"SHA256 sau: {after_hash}",
        f"Backup mã nguồn: {backup_router}",
        f"Backup database: {backup_db if db_path.is_file() else 'không có'}",
        f"Database integrity_check sau cài: {integrity2}",
        f"Database foreign_key_check sau cài: {fk_count2} lỗi",
        "",
        "ĐÃ CHỐT:",
        "1. Khóa trường: giữ nguyên quy tắc phải hoàn thành 100% phiếu.",
        "2. Khóa xã: chỉ khi 100% phiếu toàn địa bàn hoàn thành và tất cả trường có phiếu đã khóa.",
        "3. Khóa Sở: chỉ khi tất cả xã/phường trong năm học đã khóa cấp xã.",
        "4. Mở trường bị chặn khi xã hoặc Sở đang khóa.",
        "5. Mở xã bị chặn khi Sở đang khóa.",
        "6. Các thao tác GET/xem dữ liệu/báo cáo vẫn không bị cơ chế khóa chặn.",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8-sig")

    print("\n" + "=" * 100)
    print("CÀI ĐẶT THÀNH CÔNG")
    print("=" * 100)
    print("Đã sửa đúng 1 file:")
    print(f"  {router_path}")
    print("Không thay đổi cấu trúc database.")
    print(f"Báo cáo: {report_path}")
    print("\nBước tiếp theo:")
    print("1. Khởi động lại Uvicorn.")
    print("2. Với đợt #114 hiện đang 5/6 phiếu: thử Khóa trường phải BỊ TỪ CHỐI.")
    print("3. Hoàn thành phiếu thứ 6 rồi thử khóa từng trường có phiếu.")
    print("4. Sau khi các trường có phiếu đều khóa, mới thử Khóa toàn xã.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("\nDỪNG AN TOÀN - KHÔNG TIẾP TỤC CÀI.")
        print(f"Lỗi: {exc}")
        raise
