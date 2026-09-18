"""Run with python -m unittest tools.test_classroom_levels."""
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import SchoolYear
from app.report_input_models import SchoolNetworkYearData as Network
from app.routers.classrooms import level_school_ids


class ClassroomLevelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SchoolYear.__table__.create(self.engine)
        Network.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            SchoolYear(id=10, code="2025-2026", name="Previous"),
            SchoolYear(id=2, code="2026-2027", name="Current"),
            SchoolYear(id=3, code="2027-2028", name="Future"),
        ])
        for school, year, level in [
            (1, 10, "TH"), (2, 2, "TH"),
            (3, 10, "THCS"), (4, 2, "THCS"),
            (5, 10, "TH"), (5, 2, "THCS"),
            (6, 2, "TH"), (6, 2, "THCS"),
            (7, 3, "TH"),
        ]:
            self.db.add(Network(school_id=school, school_year_id=year, level_code=level))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_partial_current_year_keeps_each_schools_latest_levels(self):
        self.assertEqual(level_school_ids(self.db, "TH", 2), {1, 2, 6})
        self.assertEqual(level_school_ids(self.db, "THCS", 2), {3, 4, 5, 6})

    def test_historical_year_does_not_use_future_classification(self):
        self.assertEqual(level_school_ids(self.db, "TH", 10), {1, 5})
        self.assertEqual(level_school_ids(self.db, "THCS", 10), {3})


if __name__ == "__main__":
    unittest.main()
