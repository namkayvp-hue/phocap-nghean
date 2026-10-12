# Biểu mẫu từ Các phụ lục.pdf

Menu Xóa mù chữ có 5 mục phụ lục theo thứ tự 6.5.1–6.5.5 đối với Sở/quản trị
(các vai trò khác theo số thứ tự menu Báo cáo hiện có). Mỗi mục dẫn đến nhóm
thẻ tương ứng. Phụ lục 4 (biên bản tự kiểm tra, 3 trang) và 5 (báo cáo kết quả,
4 trang) lấy từ `Biểu mẫu Xóa mù/Mấu biểu 1.pdf`, tải PDF riêng, giữ nguyên
bố cục và nội dung. Có thêm xuất Word có số liệu. Tạo lại PDF và JSON nguồn bằng
`python -m tools.build_xmc_document_appendices`.

Nguồn: tệp `C:\PhoCap\Biểu mẫu Xóa mù\Các phụ lục.pdf` do người dùng cung cấp (28 trang).
Giữ nguyên nội dung mẫu, bao gồm số thông tư, ngày tháng chưa điền và số cột
trùng `(10)` trong mẫu 08/XMC. PDF biểu mẫu còn để trống số thông tư;
không tự bổ sung số hoặc coi đây là thông tư đã ban hành.

- `Cac_phu_luc_2026.xlsx`: danh mục và 23 trang tính chuyển từ 28 trang PDF,
  bao gồm cả phụ lục 1 (phiếu điều tra), 2 (giáo dục bắt buộc), 3 (XMC).
- `Phu_luc_3_Xoa_mu_chu.xlsx`: trang 14–28, danh mục và 9 mẫu XMC.
- `Mau_01_XMC.xlsx` đến `Mau_09_XMC.xlsx`: từng mẫu riêng.
- `Phu_luc_1_Phieu_dieu_tra.xlsx`: phiếu điều tra (2 trang nguồn).
- `Phu_luc_2_Giao_duc_bat_buoc.xlsx`: danh mục và đủ 8 biểu; mỗi biểu cũng
  có tệp `Mau_<ký hiệu>.xlsx` riêng. Có nút tổng hợp riêng từng biểu hoặc cả bộ.

Nội dung là văn bản và ô Excel có thể chỉnh sửa, không phải ảnh chụp.
Các bảng giữ ô gộp, tiêu đề nhóm, dòng trống, ghi chú và phần ký xác nhận.
Mẫu 01/XMC ghép trang 15–17, mẫu 07/XMC ghép trang 23–26: mỗi mẫu chỉ có
một trang tính liền mạch, giữ đầy đủ hàng tuổi, cộng nhóm và chữ ký cuối bảng.
Tiêu đề bảng lặp khi in, A3 ngang, vừa một trang theo chiều rộng và tự sang
trang theo chiều dài; không chia nhỏ biểu theo số trang PDF. Tệp mẫu trống
khác với báo cáo có số liệu xuất từ chức năng tổng hợp.

Tạo lại: cài `pymupdf==1.28.2` (chỉ dùng khi chuyển đổi) và chạy
`python -m tools.convert_appendices_pdf` tại thư mục dự án.
Máy chủ tải mẫu và tổng hợp số liệu bằng các tệp `.xlsx`, không cần thư viện PDF.

## Tổng hợp Phụ lục 2, 4 và 5

- `compulsory_report_data.py`: dân số và các chỉ tiêu TH/THCS từ hồ sơ năm học
  trong phạm vi của router XMC. Nguồn đội ngũ, mạng lưới, dữ liệu nhập biểu
  chỉ dùng đúng năm học; trường/giáo viên giới hạn trường tài khoản.
- `compulsory_appendix_reports.py`: điền đủ 8 mẫu PL2, giữ bố cục Excel,
  mở rộng danh sách trường/người, tính lại tổng và tỷ lệ; kèm trang kiểm tra.
- `appendix_narrative_reports.py`: DOCX có thể chỉnh sửa, giữ các phần nội dung
  mẫu nguồn; điền chỉ tiêu dân số, học tập, XMC và bảng đối chiếu đội ngũ/CSVC.
  Dùng cùng dữ liệu và phép tính như PL2/PL3; không cần cài thư viện Word.
- Tuyến xuất: `/bao-cao/xoa-mu-chu/phu-luc/{code}/tong-hop` với mã 8 biểu,
  `bo-pl2`, `pl4`, `pl5`; nhận bộ lọc năm học/xã/trường giống PL3.
- Không suy năm hoặc trường hoàn thành từ trường/năm đang học. Không suy
  nhận xét, kinh phí, quyết định công nhận hoặc chữ ký. Thiếu nguồn được
  ghi rõ để bổ sung; không gán 0. Danh sách hoàn thành lấy mọi hồ sơ được
  xác nhận hoàn thành trong tập dữ liệu năm học, không tự nhận là tốt nghiệp
  mới trong năm. Cột hoàn thành của mẫu 08 sửa nhãn THCS theo tiêu đề biểu.
- Số liệu phản ánh hồ sơ hiện tại tại thời điểm xuất; không giả lập bản chốt
  lịch sử ngày 30/9. Dữ liệu gốc và biểu mẫu trống vẫn được giữ nguyên.

Kiểm tra: `python -m unittest tools.test_compulsory_appendix_reports.NewAppendixTests`.

## Tổng hợp dữ liệu theo năm học

Trong Báo cáo → Xóa mù chữ, chọn năm học, xã/phường và trường, rồi chọn
“Xuất báo cáo có số liệu” hoặc “Tổng hợp cả bộ 9 mẫu”. Các tệp mẫu trống
vẫn được giữ nguyên để tải riêng. Máy chủ tạo một bản Excel mới trong bộ nhớ.

Phạm vi: Sở/ADMIN/phòng ban xem toàn tỉnh hoặc phạm vi đã chọn; xã giới hạn
địa bàn của tài khoản; trường giới hạn phiếu được giao cho nhân sự trường;
giáo viên giới hạn phiếu được giao trực tiếp. Phòng ban không được cập nhật.
Mỗi người tính một lần theo ID hồ sơ, ưu tiên bản đã rà soát rồi bản cập nhật
mới nhất trong năm và trong phạm vi. Không gộp người khác ID chỉ vì trùng tên.
Người chuyển đi hoặc ngừng theo dõi không nằm trong dân số đang tổng hợp.

- Tuổi = năm đầu của năm học trừ năm sinh. Mẫu 01/02/03/04/05/06/08/09
  dùng độ tuổi 15–60; mẫu 07 dùng 0–60 theo mẫu. Nhóm 15–35 nằm trong 15–60.
- Điều 23 Nghị định 353/2026/NĐ-CP: mức 1 từ hoàn thành giai đoạn 1 XMC
  hoặc lớp 3; mức 2 từ hoàn thành giai đoạn 2 XMC hoặc chương trình tiểu học.
  Bổ sung `completed_stage1/2` trong JSON của `xmc_year_evidence`; dùng
  `completed_primary_program` đã có. Kế thừa chỉ báo mức 1/2
  `completed_grade_3/5` theo quy ước có sẵn (quy định chuyển tiếp Điều 47).
  Không ghi đè bất kỳ trường cũ nào. Xác nhận tái mù loại khỏi số đạt hiện tại.
  Giá trị chưa xác định không được đổi thành chưa đạt, số 0 hoặc 100%.
- Mẫu 01 mặc định cột “Đạt chuẩn biết chữ” là đạt từ mức 1 trở lên theo
  Điều 23; có bộ chọn mức 2 để tổng hợp riêng. Quy ước lựa chọn được ghi
  trong trang kiểm tra vì tiêu đề PDF không chỉ rõ mức tại cột chung này.
- Mẫu 02 lấy danh sách có xác nhận chưa đạt một trong hai mức, kèm định danh,
  địa chỉ, chủ hộ. Mẫu 03/04 tổng hợp theo xã, nhóm tuổi và giới tính/dân tộc.
- Mẫu 05/06 lấy học viên và công nhận **trong năm** từ Dữ liệu bổ sung XMC,
  không lấy tổng dân số biết chữ làm số học viên.
- Mẫu 07 dùng tình trạng học, lớp hiện tại, xác nhận hoàn thành chương trình
  và khuyết tật. Không suy cấp/lớp học từ tuổi.
- Mẫu 08 chỉ đưa người được xác nhận tái mù chữ và thông tin hỗ trợ bổ sung.
- Mẫu 09 dùng `app/services/xmc_rules_353.py`, Điều 24–25: mức 1 và mức 2
  đều yêu cầu ít nhất 90% người 15–60 đạt mức tương ứng; xã đặc biệt khó khăn
  dùng 15–35. So sánh tỷ lệ trước làm tròn. Nhóm không có dân số hoặc thiếu
  dữ liệu không được kết luận đạt. Phạm vi trường/giáo viên không xét chuẩn xã.
  Số xã cuối biểu là số đáp ứng chỉ tiêu tính toán, không phải số đã có quyết
  định công nhận. Cấp tỉnh cần 100% xã được công nhận mức tương ứng, không
  suy từ tỷ lệ dân số toàn tỉnh. Kết quả tính không thay quyết định công nhận.
- Tỷ lệ = số lượng / dân số hoặc học viên tương ứng × 100, làm tròn 2 chữ số;
  dòng tổng tính lại tỷ lệ từ tổng tử/mẫu số, không cộng các phần trăm.
  Excel lưu tỷ lệ dạng số 0–1; hiển thị `20%`, `6,25%`, không hiển thị `20,00%`.

Căn cứ đối chiếu: `353_2026_nd-cp_11092026-signed-1-.signed.pdf`, trang 9–10
(Điều 21, 23–25), trang 16 (Điều 36), trang 23 (chuyển tiếp dữ liệu).
Nghị định có hiệu lực 01/11/2026. Các biểu mới được tính theo bộ quy tắc này
để chuẩn bị áp dụng; trước ngày hiệu lực, trang kiểm tra ghi rõ tính thử.
Giữ nguyên bộ quy tắc báo cáo cũ. Bốn mục 6.5.1–6.5.4 được ẩn khỏi menu
và trung tâm XMC; giữ nguyên mã, tuyến tải, dữ liệu và chức năng cũ.
Nguồn xác minh: https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-353-2026-nd-cp-ve-pho-cap-giao-duc-mam-non-giao-duc-bat-buoc-xoa-mu-chu-119260915094101062.htm

Trang `Kiem_tra_du_lieu` ghi nguồn, phạm vi, quy ước và hồ sơ còn thiếu.
Các bảng danh sách tự mở rộng, giữ định danh dưới dạng văn bản và không
thực thi nội dung người dùng như công thức Excel.

Dữ liệu bổ sung lưu tại bảng mới `xmc_year_evidence`, gắn với hồ sơ năm học,
có người và thời điểm cập nhật. Bảng được tạo khi khởi động; không sửa các
cột/hồ sơ cũ. Kiểm tra phạm vi, khóa đợt, quyền ghi và phiên biểu mẫu khi lưu.
Chạy thêm `python -m unittest tools.test_xmc_auto_reports tools.test_xmc_scope tools.test_xmc_rules_353`.

Kiểm tra: `python -m unittest tools.test_xmc_appendices`.
Bộ kiểm tra đối chiếu toàn bộ từ trong từng trang PDF với ô Excel,
kiểm tra số trang tính và các đường tải mẫu theo quyền truy cập.
