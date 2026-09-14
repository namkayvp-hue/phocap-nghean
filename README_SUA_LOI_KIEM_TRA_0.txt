SỬA LỖI KIỂM TRA GIÁ TRỊ 0

Bản trước dùng:
    enrich.get("remaining_missing_source_codes") or -1

Khi giá trị hợp lệ là 0, biểu thức trên lại trả về -1 và bộ cài dừng nhầm.
Bản này kiểm tra 0 trực tiếp, đồng thời xác nhận:
- recovered_source_codes = 60
- remaining_missing_source_codes = 0
- unresolved_source_codes = 0

Bộ cài không thực hiện sáp nhập và không chủ động ghi phocap.db.
