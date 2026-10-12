import json
import unittest
from datetime import date
from io import BytesIO
from zipfile import ZipFile
from xml.etree import ElementTree as ET
from openpyxl import load_workbook
from app.models import School
from app.survey_models import SurveyPerson, SurveyPersonYearRecord
from app.report_input_models import SchoolNetworkYearData, SchoolStructuredReportInput
from app.xmc_appendices import COMPULSORY_FORMS
from tools.test_xmc_scope import ScopeTests


class NewAppendixTests(unittest.TestCase):
    def setUp(self):
        self.fixture=ScopeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db=self.fixture.db
        self.client=self.fixture.client
        self.fixture.user['role_code']='ADMIN'
        for i, age, grade in [(1,6,1),(2,11,5),(3,15,9)]:
            p=self.db.get(SurveyPerson,i)
            p.date_of_birth=date(2026-age,1,1)
            r=self.db.get(SurveyPersonYearRecord,i)
            r.learning_status='DANG_HOC'
            r.class_name_reported=f'{grade}A'
            r.school_name_reported='THCS Test' if grade>=6 else 'Tieu hoc Test'
            r.completed_primary_program=i>=2
            r.completed_lower_secondary_program=i==3
            r.disability_status='KHONG_KHUYET_TAT'
            r.study_location_scope='TAI_CHO'
            r.current_education_program='GDTX' if i==3 else 'CHUA_XAC_DINH'
            r.post_lower_secondary_path='CHUA_XAC_DINH'
        self.db.commit()

    def response(self, code, query=''):
        response=self.client.get(f'/bao-cao/xoa-mu-chu/phu-luc/{code}/tong-hop?school_year_id=1'+query)
        self.assertEqual(response.status_code,200,response.text[:200] if response.status_code!=200 else '')
        return response

    def workbook(self,code,query=''):
        return load_workbook(BytesIO(self.response(code,query).content))

    def resources(self):
        for i in range(1,8):
            s=self.db.get(School,i)
            if not s:
                s=School(id=i,code=f'NEW{i}',name=f'School {i}',commune_id=1)
                self.db.add(s)
                self.db.flush()
            for level in ['TH','THCS']:
                self.db.add(SchoolNetworkYearData(school_id=i,school_year_id=1,level_code=level,
                    data_json=json.dumps(dict(class_total=i,teachers=2*i,rooms_permanent=i,rooms_semi_permanent=0,rooms_temporary=0))))
                self.db.add(SchoolStructuredReportInput(school_id=i,school_year_id=1,form_code=level+'_01_CSVC',
                    data_json=json.dumps(dict(room_rent_borrow=0,school_site_count=1))))
        # A different year must not override current figures.
        self.db.add(SchoolNetworkYearData(school_id=1,school_year_id=2,level_code='TH',data_json='{"teachers":999,"class_total":999}'))
        self.db.commit()

    def test_all_eight_forms_bundle_and_population_values(self):
        for code,_,pages in COMPULSORY_FORMS:
            wb=self.workbook(code)
            self.assertEqual(len(wb.sheetnames),len(pages)+1)
        wb=self.workbook('bo-pl2')
        self.assertEqual(len(wb.sheetnames),12)
        self.assertEqual(wb['Trang_04']['F9'].value,1)
        self.assertEqual(wb['Trang_04']['L9'].value,1)
        self.assertEqual(wb['Trang_05']['F11'].value,1)
        self.assertEqual(wb['Trang_05']['G11'].value,1)
        self.assertEqual(wb['Trang_05']['G11'].number_format,'0%')
        self.assertEqual(wb['Trang_09']['N9'].value,1)
        self.assertEqual(wb['Trang_09']['O26'].value,1)  # 15-year-old, grade 9, GDTX
        self.assertEqual(wb['Trang_10']['L20'].value,1)
        self.assertEqual(wb['Trang_10']['M20'].value,1)

    def test_school_rows_expand_and_weighted_totals(self):
        self.resources()
        wb=self.workbook('bo-pl2')
        # 7 rows exceed every original template capacity.
        self.assertEqual(wb['Trang_06']['I19'].value,56)
        self.assertEqual(wb['Trang_06']['P19'].value,2)
        self.assertEqual(wb['Trang_07']['J18'].value,28)
        self.assertEqual(wb['Trang_07']['AB18'].value,1)
        self.assertEqual(wb['Trang_11']['H18'].value,56)
        self.assertEqual(wb['Trang_11']['O18'].value,2)
        self.assertEqual(wb['Trang_12']['D19'].value,28)
        self.assertEqual(wb['Trang_12']['H19'].value,1)
        for page in [6,7,11,12]:
            self.assertEqual(wb[f'Trang_{page:02d}'].page_setup.fitToHeight,0)

    def test_missing_data_does_not_become_zero(self):
        self.db.get(SurveyPersonYearRecord,1).completed_primary_program=None
        self.db.commit()
        ws=self.workbook('01-TH_TN')['Trang_04']
        self.assertIsNone(ws['F31'].value)
        self.assertEqual(ws['F12'].value,0)  # explicit no disability
        self.db.get(SurveyPerson,1).date_of_birth=None
        self.db.commit()
        self.assertIsNone(self.workbook('01-TH_TN')['Trang_04']['F9'].value)

    def test_completion_list_is_confirmed_and_safe(self):
        self.db.get(SurveyPerson,2).full_name='=1+1'
        self.db.commit()
        ws=self.workbook('04-TH_HT')['Trang_08']
        self.assertEqual(ws['B9'].value,'=1+1')
        self.assertEqual(ws['B9'].data_type,'s')
        self.assertIsNone(ws['H9'].value)
        self.assertIsNone(ws['I9'].value)
        self.assertNotIn('Person 1',[c.value for row in ws for c in row])

    def test_word_is_valid_and_has_numbers_and_template_sections(self):
        for code in ['pl4','pl5']:
            response=self.response(code)
            self.assertIn('wordprocessingml',response.headers['content-type'])
            with ZipFile(BytesIO(response.content)) as z:
                self.assertIsNone(z.testzip())
                root=ET.fromstring(z.read('word/document.xml'))
                text=' '.join(root.itertext())
                self.assertIn('1/1',text)
                self.assertIn('100%',text)
                self.assertIn('THÔNG TIN CẦN HOÀN THIỆN',text)
                self.assertIn('Trong đó số người mù chữ:',text)
                self.assertIn('KIẾN NGHỊ',text)

    def test_all_exports_reject_forged_scope_and_year(self):
        self.fixture.user['role_code']='GIAO_VIEN'
        for code in [c for c,_,_ in COMPULSORY_FORMS]+['bo-pl2','pl4','pl5']:
            base=f'/bao-cao/xoa-mu-chu/phu-luc/{code}/tong-hop'
            self.assertEqual(self.client.get(base+'?school_year_id=1&school_id=2').status_code,403)
            self.assertEqual(self.client.get(base+'?school_year_id=999').status_code,422)
        self.resources()
        ws=self.workbook('02-TH_GV')['Trang_06']
        self.assertEqual(ws['I12'].value,2)
        self.assertIsNone(ws['B13'].value)
        self.fixture.user['role_code']='PHONG_BAN'
        self.assertEqual(self.workbook('02-TH_GV')['Trang_06']['I19'].value,56)


if __name__=='__main__':
    unittest.main()
