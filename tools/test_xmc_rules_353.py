import unittest
from types import SimpleNamespace as NS
from app.services.xmc_rules_353 import personal_levels, commune_level
from tools.test_xmc_auto_reports import person


class Rules353Tests(unittest.TestCase):
    def test_both_completion_pathways_and_legacy_preservation(self):
        _, record = person(1, g1=False, g2=False)
        self.assertEqual(personal_levels(record, {"completed_stage1": True})[:2], (True, False))
        self.assertEqual(personal_levels(record, {"completed_stage2": True})[:2], (True, True))
        self.assertFalse(record.completed_grade_3)
        self.assertFalse(record.completed_grade_5)
        record.completed_primary_program = True
        self.assertEqual(personal_levels(record, {})[:2], (True, True))
        self.assertEqual(personal_levels(record, {"relapsed": True}), (False, False, False))
        self.assertTrue(personal_levels(record, {"illiterate": True})[2])
        self.assertEqual(personal_levels(None, {}), (None, None, False))
        self.assertEqual(personal_levels(None, {"completed_stage1": False})[:2], (None, None))

    def test_normal_commune_uses_15_60_for_both_levels(self):
        items = [dict(age=20, g1=True, g2=True)] * 9 + [dict(age=60, g1=False, g2=False)]
        self.assertEqual(commune_level(items, False), 2)  # exactly 90%
        self.assertEqual(commune_level(items + [dict(age=60, g1=False, g2=False)], False), "Chưa đạt")
        self.assertEqual(commune_level(items + [dict(age=61, g1=False, g2=False)], False), 2)

    def test_special_commune_uses_15_35_not_15_25(self):
        items = [dict(age=15, g1=True, g2=False)] * 9 + [dict(age=35, g1=False, g2=False)] * 2
        self.assertEqual(commune_level(items, True), "Chưa đạt")
        self.assertEqual(commune_level(items[:10] + [dict(age=36, g1=False, g2=False)], True), 1)

    def test_missing_and_threshold_before_rounding(self):
        self.assertEqual(commune_level([], False), "Chưa đủ dữ liệu")
        self.assertEqual(commune_level([dict(age=None, g1=True, g2=True)], False), "Chưa đủ dữ liệu")
        self.assertEqual(commune_level([dict(age=15, g1=None, g2=None)], False), "Chưa đủ dữ liệu")
        self.assertEqual(commune_level([dict(age=15, g1=True, g2=True)], None), "Chưa đủ dữ liệu")
        items = [dict(age=20, g1=True, g2=True)] * 89999 + [dict(age=20, g1=False, g2=False)] * 10001
        self.assertEqual(round(100 * 89999 / 100000, 2), 90)
        self.assertEqual(commune_level(items, False), "Chưa đạt")


if __name__ == "__main__":
    unittest.main()
