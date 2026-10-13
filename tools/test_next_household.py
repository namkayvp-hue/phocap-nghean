import unittest
from unittest.mock import patch
from app.routers import surveys


class NextHouseholdTests(unittest.TestCase):
    def target(self, rows, current):
        with patch.object(surveys, 'lay_chuoi_phieu_nhap_nhanh', return_value=rows) as scoped:
            result=surveys.next_unfinished_household_url(db='db', request='request', batch_id=8,
                                                       household_id=current, school_year_id=2)
            scoped.assert_called_once_with(db='db',request='request',batch_id=8)
            return result

    def test_next_pending_and_preserved_year(self):
        rows=[dict(household_id=i,form_status=status) for i,status in
              [(1,'DA_HOAN_THANH'),(2,'DA_HOAN_THANH'),(3,'DANG_NHAP')]]
        self.assertEqual(self.target(rows,1),'/dieu-tra/8/ho-dan/3/nhap-nhanh?school_year_id=2&status=quick_saved_next#members')

    def test_last_household_and_unfinished_earlier_household(self):
        rows=[dict(household_id=1,form_status='DANG_NHAP'),dict(household_id=2,form_status='DA_HOAN_THANH')]
        self.assertIn('/ho-dan/1/',self.target(rows,2))
        rows[0]['form_status']='DA_HOAN_THANH'
        self.assertIsNone(self.target(rows,2))

    def test_empty_or_current_outside_scope(self):
        self.assertIsNone(self.target([],1))
        self.assertIsNone(self.target([dict(household_id=2,form_status='DANG_NHAP')],1))


if __name__ == '__main__': unittest.main()
