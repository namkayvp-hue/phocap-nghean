import unittest
from datetime import date
from openpyxl import load_workbook
from app.xmc_appendices import TEMPLATE_DIR
from app.services.report_export_date import stamp_date_text, stamp_workbook


class ExportDateTests(unittest.TestCase):
    def test_all_report_templates_and_split_date(self):
        wb = load_workbook(TEMPLATE_DIR / 'Cac_phu_luc_2026.xlsx')
        legal = wb['Trang_03']['B4'].value
        stamp_workbook(wb, date(2027, 1, 2))
        self.assertEqual(wb['Trang_05']['M9'].value, '…………., ngày 02 tháng 01')
        self.assertEqual(wb['Trang_05']['N10'].value, 'năm 2027')
        self.assertIn('ngày 02 tháng 01 năm 2027', wb['Trang_15']['P68'].value)
        self.assertEqual(wb['Trang_09']['J5'].value, 'Thời điểm xuất: 02/01/2027')
        self.assertEqual(wb['Trang_03']['B4'].value, legal)
        self.assertEqual(wb['Trang_08']['C8'].value, 'Ngày tháng\nnăm sinh')

    def test_word_dateline_preserves_event_and_period_dates(self):
        self.assertEqual(stamp_date_text('…., ngày ... tháng ... năm ...',date(2027,1,2)),
                         '…., ngày 02 tháng 01 năm 2027')
        for text in ['Hôm nay, lúc .. giờ … phút, ngày … tháng … năm …, tại …',
                     '(Từ ngày ... tháng ... năm ... đến ngày ... tháng ... năm ...)',
                     'Thông tư ngày ... tháng ... năm 2026']:
            self.assertEqual(stamp_date_text(text,date(2027,1,2)),text)


if __name__ == '__main__':
    unittest.main()
