"""Run: .venv/Scripts/python -m unittest tools.test_person_excel_import"""
import re
import tempfile
import unittest
from contextlib import closing
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_db
from app.household_import_models import HouseholdImportJob
from app.routers import person_excel_import as route
from app.services import person_excel_import as service
from app.survey_models import SurveyBatch, SurveyForm, SurveyPerson, SurveyPersonYearRecord
from app.survey_workflow_models import SurveyCommuneExecutionState
from app.routers.xmc_appendix_reports import load_people
from app.routers.report_center import _th_m1_load_people_and_records, _th_m1_build_metrics
from app.routers.survey_summary_report import _load_person_rows
from starlette.requests import Request
from tools.test_xmc_scope import ScopeTests


class PersonImportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ScopeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db = self.fixture.db
        self.batch = self.db.get(SurveyBatch, 1)
        self.user = dict(id=1, role_code='ADMIN', full_name='Admin')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(route, 'ROOT', Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key='test-person-import')
        @app.middleware('http')
        async def auth(request, call_next):
            request.scope['auth_user'] = self.user
            return await call_next(request)
        app.dependency_overrides[get_db] = lambda: self.db
        app.include_router(route.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.home = self.client.get(route.PREFIX + '?batch_id=1')
        self.assertEqual(self.home.status_code, 200)
        self.csrf = re.search(r'name="csrf" value="([^"]+)"', self.home.text)[1]

    def file(self, people=None, edits=None):
        wb = load_workbook(BytesIO(service.make_template(self.batch)))
        ws = wb['MauNhapLieu']
        defaults = {'Họ đệm':'Nguyễn Văn', 'Tên':'An', 'Ngày':1, 'Tháng':1, 'Năm sinh':2014,
                    'Nữ':'Không', 'Chủ hộ - Họ đệm':'Nguyễn Văn', 'Chủ hộ - Tên':'Bình',
                    'Địa chỉ: Số nhà, tên đường, tổ (nếu có)':'Thôn A', 'Số phiếu':'NEW1',
                    'Số định danh':'001234567890', 'Tình trạng học tập':'Đang học',
                    'Mã Trường':'S1', 'Tên trường':'School 1', 'Lớp học':'6A',
                    'Hoàn thành tiểu học':'Có', 'Năm hoàn thành tiểu học':2025}
        for index, overrides in enumerate(people or [{}], 6):
            values = dict(defaults, **overrides)
            for col, header in enumerate(service.BASE_HEADERS + service.EXTRA_HEADERS, 1):
                ws.cell(index, col).value = values.get(header)
        if edits:
            edits(wb)
        output = BytesIO()
        wb.save(output)
        return output.getvalue()

    def preview(self, content=None, mode='complete'):
        return self.client.post(route.PREFIX + '/xem-truoc', data=dict(batch_id=1, csrf=self.csrf, mode=mode), files={'excel_file':('detail.xlsx', content or self.file())})

    def confirm(self, preview):
        token = re.search(r'name="token" value="([^"]+)"', preview.text)[1]
        return self.client.post(route.PREFIX + '/xac-nhan', data=dict(csrf=self.csrf, token=token, acknowledge='yes'), follow_redirects=False)

    def count(self):
        return self.db.scalar(select(func.count(SurveyPerson.id)))

    def test_preview_confirm_reports_and_idempotence(self):
        before = self.count()
        preview = self.preview()
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(self.count(), before, 'Preview cannot write people')
        self.assertEqual(self.confirm(preview).status_code, 303)
        person = self.db.scalar(select(SurveyPerson).where(SurveyPerson.personal_id == '001234567890'))
        self.assertIsNotNone(person)
        form = self.db.scalar(select(SurveyForm).where(SurveyForm.form_number == 'NEW1'))
        record = self.db.scalar(select(SurveyPersonYearRecord).where(SurveyPersonYearRecord.survey_person_id == person.id))
        self.assertEqual(form.status, 'DA_HOAN_THANH')
        self.assertTrue(record.completed_primary_program)
        self.assertEqual(record.primary_completion_year, 2025)
        self.assertEqual(record.school_id, 1)
        request = Request({'type':'http','auth_user':self.user})
        self.assertIn(person.id, {p.id for p, _ in load_people(self.db, self.user, 1)})
        # The same record feeds existing summary and primary-school loaders.
        summary_rows = _load_person_rows(db=self.db, request=request, batch_ids=[1], school_year_id=1, school_id=None, completed_only=True)
        self.assertIn(person.id, {r['person_id'] for r in summary_rows})
        report_rows = _th_m1_load_people_and_records(db=self.db, request=request, school_year_id=1, selected_commune_id=None, selected_school_id=None)
        self.assertIn(person.id, {p.id for p, _ in report_rows})
        metrics = _th_m1_build_metrics(people_and_records=report_rows, reference_year=2026, reporting_commune_id=1)
        self.assertEqual(metrics[12]['total'], 1)
        self.assertEqual(self.confirm(preview).status_code, 409)
        preview2 = self.preview()
        self.assertEqual(self.confirm(preview2).status_code, 303)
        self.assertEqual(self.count(), before + 1)
        self.assertEqual(self.db.scalar(select(func.count(HouseholdImportJob.id))), 2)

    def test_draft_excluded_from_reports(self):
        preview = self.preview(mode='draft')
        self.assertEqual(self.confirm(preview).status_code, 303)
        person = self.db.scalar(select(SurveyPerson).where(SurveyPerson.personal_id == '001234567890'))
        self.assertNotIn(person.id, {p.id for p, _ in load_people(self.db, self.user, 1)})

    def test_bad_file_is_atomic(self):
        before = self.count()
        response = self.preview(self.file([{}, {'Tên':'Sai', 'Số định danh':'other', 'Năm sinh':11}]))
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('name="token"', response.text)
        self.assertEqual(self.count(), before)

    def test_duplicate_person_and_wrong_commune(self):
        self.assertEqual(self.preview(self.file([{}, {}])).status_code, 422)
        self.assertEqual(self.preview(self.file(edits=lambda wb: setattr(wb['MauNhapLieu']['E1'], 'value', 'wrong'))).status_code, 422)

    def test_admin_only_and_csrf(self):
        for role in ('XA', 'TRUONG', 'GIAO_VIEN', 'PHONG_BAN'):
            self.user['role_code'] = role
            self.assertEqual(self.client.get(route.PREFIX).status_code, 403)
            self.assertEqual(self.client.get(route.PREFIX + '/mau-excel?batch_id=1').status_code, 403)
            self.assertEqual(self.preview().status_code, 403)
        self.user['role_code'] = 'ADMIN'
        self.csrf = 'wrong'
        self.assertEqual(self.preview().status_code, 403)

    def test_lock_and_concurrent_changes_rechecked(self):
        preview = self.preview()
        self.db.add(SurveyCommuneExecutionState(survey_batch_id=1, is_commune_locked=True))
        self.db.commit()
        self.assertEqual(self.confirm(preview).status_code, 409)
        self.assertEqual(self.count(), 3)
        self.db.query(SurveyCommuneExecutionState).delete()
        self.db.commit()
        preview = self.preview()
        self.batch.notes = 'Changed since preview'
        self.db.commit()
        self.assertEqual(self.confirm(preview).status_code, 409)

    def test_preserve_optional_values_and_other_people(self):
        self.assertEqual(self.confirm(self.preview()).status_code, 303)
        record = self.db.scalar(select(SurveyPersonYearRecord).join(SurveyPerson).where(SurveyPerson.personal_id == '001234567890'))
        record.attends_regularly = True
        record.notes = 'Existing detail'
        self.db.commit()
        content = self.file([{'Hoàn thành tiểu học':None, 'Năm hoàn thành tiểu học':None, 'Mã Trường':None, 'Tên trường':None, 'Lớp học':None}])
        self.assertEqual(self.confirm(self.preview(content)).status_code, 303)
        self.db.refresh(record)
        self.assertTrue(record.completed_primary_program)
        self.assertTrue(record.attends_regularly)
        self.assertEqual(record.notes, 'Existing detail')
        self.assertEqual(record.school_id, 1)
        self.assertEqual(self.db.get(SurveyPerson, 2).full_name, 'Person 2')

    def test_partial_household_cannot_be_completed(self):
        self.assertEqual(self.confirm(self.preview()).status_code, 303)
        person = self.db.scalar(select(SurveyPerson).where(SurveyPerson.personal_id == '001234567890'))
        self.db.add(SurveyPerson(code='EXTRA', household_id=person.household_id, full_name='Other member', date_of_birth=date(2000,1,1), gender='Nam'))
        self.db.commit()
        response = self.preview()
        self.assertEqual(response.status_code, 422)
        self.assertIn('thiếu thành viên', response.text)

    def test_failure_rolls_back_all_changes(self):
        preview = self.preview()
        apply = service.apply_plan
        def fail(*args):
            apply(*args)
            raise RuntimeError('simulated failure')
        with patch.object(service, 'apply_plan', side_effect=fail), self.assertLogs(route.logger, level='ERROR'):
            self.assertEqual(self.confirm(preview).status_code, 500)
        self.assertEqual(self.count(), 3)
        self.assertEqual(self.db.scalar(select(func.count(HouseholdImportJob.id))), 0)

    def test_extended_report_fields_and_false_values(self):
        content = self.file([{'Học hòa nhập':'Không', 'Trình độ học vấn':'Tiểu học', 'Lớp cao nhất đã hoàn thành':5,
                             'Phạm vi nơi học':'Tại chỗ', 'Tình trạng khuyết tật':'Không khuyết tật'}])
        self.assertEqual(self.confirm(self.preview(content)).status_code, 303)
        record = self.db.scalar(select(SurveyPersonYearRecord).join(SurveyPerson).where(SurveyPerson.personal_id == '001234567890'))
        self.assertIs(record.inclusive_education, False)
        self.assertEqual(record.highest_completed_grade, 5)
        self.assertEqual(record.education_attainment_level, 'TIEU_HOC')
        self.assertEqual(record.study_location_scope, 'TAI_CHO')

    def test_existing_identity_in_other_household_is_rejected(self):
        self.db.get(SurveyPerson, 2).personal_id = '001234567890'
        self.db.commit()
        response = self.preview()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.count(), 3)

    def test_template_download_identifiers_and_formula_rejection(self):
        response = self.client.get(route.PREFIX + '/mau-excel?batch_id=1')
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(BytesIO(response.content))
        self.assertEqual(wb['MauNhapLieu']['V6'].number_format, '@')
        self.assertEqual(wb['MauNhapLieu'].freeze_panes, 'D6')
        self.assertIn('HuongDan', wb.sheetnames)
        response = self.preview(self.file(edits=lambda wb: setattr(wb['MauNhapLieu']['D6'], 'value', '=1+1')))
        self.assertEqual(response.status_code, 422)
        self.assertIn('chuyển công thức thành giá trị', response.text)

    def test_backup_captures_existing_database_before_write(self):
        path = Path(self.tmp.name) / 'backup_source.db'
        engine = create_engine('sqlite:///' + path.as_posix())
        try:
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE marker (value INTEGER)'))
                connection.execute(text('INSERT INTO marker VALUES (7)'))
            with Session(engine) as db:
                db.execute(text('BEGIN IMMEDIATE'))
                backup = route.backup_database(db, 'test')
                self.assertTrue(backup.is_file())
                db.execute(text('UPDATE marker SET value=8'))
                db.commit()
            import sqlite3
            with closing(sqlite3.connect(str(backup))) as connection:
                self.assertEqual(connection.execute('SELECT value FROM marker').fetchone()[0], 7)
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
