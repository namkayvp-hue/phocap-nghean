import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine, text, inspect
from app.services.survey_school_details import grade_number, validate_completion_details, ensure_school_details_schema
from tools.test_xmc_scope import ScopeTests
from app.routers import surveys
from app.survey_models import SurveyPerson, SurveyPersonYearRecord


class SchoolDetailsTests(unittest.TestCase):
    def test_grade_and_year_rules(self):
        for value, expected in [('Lớp 5A',5),('9B',9),('Lớp 4',4),('10A',10),('5 tuổi A',None),('Mẫu giáo 5 tuổi',None)]:
            self.assertEqual(grade_number(value),expected)
        year=SimpleNamespace(code='2025-2026')
        args=(date(2010,1,1),year)
        self.assertEqual(validate_completion_details(5,'CO',None,'2026',None,*args),({'primary_completion_year':2026},[]))
        self.assertTrue(validate_completion_details(4,'CO',None,'2026',None,*args)[1])
        self.assertTrue(validate_completion_details(9,None,'CO',None,'2099',*args)[1])
        self.assertTrue(validate_completion_details(9,None,'CO',None,'',*args)[1])
        self.assertEqual(validate_completion_details(10,None,None,None,None,*args),({},[]))

    def test_completion_by_age_without_matching_grade(self):
        year = SimpleNamespace(code='2026-2027')
        for age in (11, 14):
            birth = date(2026-age, 1, 1)
            self.assertEqual(validate_completion_details(None,'CO',None,'2025',None,birth,year),
                             ({'primary_completion_year':2025},[]))
        for age in (15, 18):
            birth = date(2026-age, 1, 1)
            self.assertEqual(validate_completion_details(10,None,'CO',None,'2025',birth,year),
                             ({'lower_secondary_graduation_year':2025},[]))
        self.assertTrue(validate_completion_details(None,'CO',None,'2025',None,date(2016,1,1),year)[1])
        self.assertTrue(validate_completion_details(None,None,'CO',None,'2025',date(2007,1,1),year)[1])
        self.assertTrue(validate_completion_details(None,'CO',None,'',None,date(2013,1,1),year)[1])

    def test_migration_preserves_rows_and_is_repeatable(self):
        engine=create_engine('sqlite://')
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE survey_person_year_records (id INTEGER PRIMARY KEY, notes TEXT)'))
            conn.execute(text("INSERT INTO survey_person_year_records VALUES (1,'keep')"))
        ensure_school_details_schema(engine)
        ensure_school_details_schema(engine)
        with engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT notes, primary_completion_year FROM survey_person_year_records')).one(),('keep',None))
        engine.dispose()

    def test_main_save_and_quick_address_save(self):
        with patch('app.database.SessionLocal',side_effect=AssertionError('No production database access')):
            fixture=ScopeTests(); fixture.setUp()
            try:
                fixture.user['role_code']='ADMIN'
                fixture.client.app.include_router(surveys.router)
                url='/dieu-tra/1/ho-dan/1/doi-tuong/1/nam-hoc/'
                with patch.object(surveys,'co_quyen_truy_cap_phieu',return_value=True), patch.object(surveys,'b131143_save_person_event'):
                    response=fixture.client.post(url+'luu',data=dict(school_year_id=1,learning_status='DANG_HOC',residency_status='THUONG_TRU',
                        school_name_reported='Trường Tiểu học Test',class_name_reported='5A',
                        completed_primary_program='CO',primary_completion_year='2026',
                        study_location_scope='DI_HOC_NGOAI_TINH',study_destination_address='Địa chỉ đến'),follow_redirects=False)
                    self.assertEqual(response.status_code,303,str(response.context.get('errors') or response.context.get('thong_bao_loi')) if response.status_code!=303 else '')
                    fixture.db.expire_all()
                    record=fixture.db.get(SurveyPersonYearRecord,1)
                    self.assertEqual(record.primary_completion_year,2026)
                    self.assertTrue(record.completed_primary_program)
                    self.assertEqual(record.study_destination_address,'Địa chỉ đến')
                    response=fixture.client.post(url+'luu-chi-bao-nhanh',data=dict(school_year_id=1,
                        study_location_scope='NOI_KHAC_DEN',study_origin_address='Địa chỉ đi'))
                    self.assertTrue(response.json()['ok'],response.text)
                    fixture.db.expire_all()
                    self.assertEqual(fixture.db.get(SurveyPersonYearRecord,1).study_origin_address,'Địa chỉ đi')
                    response=fixture.client.post(url+'luu',data=dict(school_year_id=1,learning_status='DANG_HOC',residency_status='THUONG_TRU',
                        school_name_reported='THCS Test',class_name_reported='6A'),follow_redirects=False)
                    self.assertEqual(response.status_code,303,response.text[:1000])
                    fixture.db.expire_all()
                    self.assertEqual(fixture.db.get(SurveyPersonYearRecord,1).primary_completion_year,2026)
                    self.assertTrue(fixture.db.get(SurveyPersonYearRecord,1).completed_primary_program)
                    response=fixture.client.post(url+'luu',data=dict(school_year_id=1,learning_status='DANG_HOC',residency_status='THUONG_TRU',
                        school_name_reported='THCS Test',class_name_reported='9A',completed_lower_secondary_program='CO',
                        lower_secondary_graduation_year='2026'),follow_redirects=False)
                    self.assertEqual(response.status_code,303)
                    fixture.db.expire_all()
                    self.assertEqual(fixture.db.get(SurveyPersonYearRecord,1).lower_secondary_graduation_year,2026)
                    person = fixture.db.get(SurveyPerson,1)
                    for birth, class_name, flag, year_field in [
                        (date(2013,1,1),'7A','completed_primary_program','primary_completion_year'),
                        (date(2010,1,1),'10A','completed_lower_secondary_program','lower_secondary_graduation_year'),
                    ]:
                        person.date_of_birth = birth
                        fixture.db.commit()
                        response=fixture.client.post(url+'luu',data=dict(school_year_id=1,learning_status='DANG_HOC',residency_status='THUONG_TRU',
                            school_name_reported='Trường Test',class_name_reported=class_name,**{flag:'CO',year_field:'2025'}),follow_redirects=False)
                        self.assertEqual(response.status_code,303,response.text[:1000])
                        fixture.db.expire_all()
                        record=fixture.db.get(SurveyPersonYearRecord,1)
                        self.assertTrue(getattr(record,flag))
                        self.assertEqual(getattr(record,year_field),2025)
                    fixture.user['role_code']='GIAO_VIEN'
                    with patch.object(surveys,'b131133_danh_gia_do_day_du_phieu_nhap_nhanh',return_value={
                        'active_people_count':1,'missing_year_record_count':0,'incomplete_year_record_count':0}), \
                        patch.object(surveys,'lay_chuoi_phieu_nhap_nhanh',return_value=[
                            dict(household_id=1,form_status='DA_HOAN_THANH'),dict(household_id=2,form_status='DANG_NHAP')]):
                        response=fixture.client.post(url+'luu',data=dict(school_year_id=1,learning_status='DANG_HOC',residency_status='THUONG_TRU',
                            school_name_reported='THCS Test',class_name_reported='9A',finish_household='1'),follow_redirects=False)
                        self.assertEqual(response.status_code,303)
                        self.assertIn('/ho-dan/2/nhap-nhanh?',response.headers['location'])
            finally:
                fixture.doCleanups()


if __name__ == '__main__': unittest.main()
