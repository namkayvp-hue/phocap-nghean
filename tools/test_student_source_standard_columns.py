import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from openpyxl import Workbook
from app.routers import student_reconciliation_source as source


class StandardSourceTests(unittest.TestCase):
    def parse(self, rows, headers=None):
        wb=Workbook(); ws=wb.active
        ws.append(['Danh sach hoc sinh']); ws.append(headers or list(source.STANDARD_SOURCE_COLUMNS))
        for row in rows: ws.append(row)
        stream=BytesIO(); wb.save(stream); wb.close()
        school=SimpleNamespace(id=1,name='School Test')
        with patch.object(source,'_school_lookup',return_value=({source._school_key(school.name):[school]},{1:school},{1:school.name})):
            return source._parse_workbook(None,stream.getvalue(),1,1)

    def row(self, personal=None):
        return [1,'Department','School Test','Grade 5','5A','Student Test','01/01/2015','Nam',
                'Birthplace','Kinh',personal,'Đang học','Address','Father',1980,'Mother',1982]

    def test_standard_columns_accept_missing_identifier_without_inventing_personal_id(self):
        result=self.parse([self.row()])
        self.assertEqual(result['errors'],[])
        record=result['records'][0]
        self.assertTrue(record['student_code'].startswith('SRC_'))
        self.assertIsNone(record['personal_id'])
        self.assertEqual(record['father_birth_year'],1980)
        self.assertEqual(len(result['warnings']),1)
        self.assertEqual(record['student_code'],self.parse([self.row()])['records'][0]['student_code'])

    def test_identifier_is_preserved(self):
        result=self.parse([self.row('012345678901')])
        self.assertEqual(result['errors'],[])
        self.assertEqual(result['records'][0]['personal_id'],'012345678901')

    def test_duplicate_rows_are_blocked(self):
        result=self.parse([self.row(),self.row()])
        self.assertTrue(result['errors'])

    def test_changed_column_order_is_not_accepted_as_standard(self):
        headers=list(source.STANDARD_SOURCE_COLUMNS)
        headers[0],headers[1]=headers[1],headers[0]
        result=self.parse([self.row()],headers)
        self.assertEqual(result['records'],[])


if __name__ == '__main__': unittest.main()
