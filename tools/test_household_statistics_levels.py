import unittest
from types import SimpleNamespace

from app.routers.household_updates import _level_from_record


class StatisticsLevelTests(unittest.TestCase):
    def test_levels(self):
        cases = [
            ("Trường MN Nghi Kim", "2 tuổi A", "MN"),
            ("", "2 tuổi A", "MN"),
            ("", "Nhóm 18-24 tháng", "MN"),
            ("Trường MN Nghi Kim", "", "MN"),
            ("Trường Mầm non", "Lớp 3 tuổi", "MN"),
            ("Trường TH Nghi Kim", "2A", "TH"),
            ("", "Lớp 6A1", "THCS"),
            ("", "12A", "THPT"),
            ("Trường số 2", "", "CHUA_XAC_DINH"),
        ]
        for school, classroom, expected in cases:
            with self.subTest(school=school, classroom=classroom):
                record = SimpleNamespace(school_name_reported=school,
                    class_name_reported=classroom, learning_status="DANG_HOC")
                self.assertEqual(_level_from_record(record, None, None), expected)


if __name__ == "__main__":
    unittest.main()
