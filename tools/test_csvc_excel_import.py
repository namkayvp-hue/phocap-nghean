"""Tests use only an in-memory database and in-memory Excel workbooks."""
import json
import re
import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware

from app.database import get_db
from app.models import School
from app.report_input_models import SchoolMn01CsvcInput, SchoolStructuredReportInput, SchoolNetworkYearData
from app.routers import csvc_excel_import as route, report_inputs as inputs
from app.services import csvc_excel_import as service
from app.pcgd_xmc_report_builders_v1 import _structured_overlay_export
from app.routers.pcgdmn_template_report import _b24311_load_mn02_csvc
from app.access_control import AccessControlMiddleware
from tools import test_xmc_scope as fixture_module


class CsvcExcelTests(unittest.TestCase):
    def setUp(self):
        fixture = fixture_module.ScopeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.db = fixture.db
        self.db.get(School, 1).name = 'MN Test'
        self.db.get(School, 2).name = 'TH Test'
        self.db.add(School(id=3, code='S3', name='THCS Test', commune_id=2))
        for school_id, level in enumerate(('MN', 'TH', 'THCS'), 1):
            self.db.add(SchoolNetworkYearData(school_id=school_id, school_year_id=1, level_code=level, data_json='{}'))
        self.db.commit()
        self.user = dict(id=1, role_code='ADMIN', full_name='Admin')
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key='csvc-test')
        @app.middleware('http')
        async def auth(request, call_next):
            request.scope['auth_user'] = self.user
            return await call_next(request)
        app.dependency_overrides[get_db] = lambda: self.db
        app.include_router(route.router)
        app.include_router(inputs.router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def url(self, level):
        return '/csvc/nhap-excel/' + level

    def sid(self, level):
        return {'MN':1, 'TH':2, 'THCS':3}[level]

    def template(self, level):
        params = dict(school_year_id=1, school_id=self.sid(level))
        home = self.client.get(self.url(level), params=params)
        self.assertEqual(home.status_code, 200, home.text)
        self.csrf = re.search(r'name="csrf" value="([^"]+)"', home.text)[1]
        response = self.client.get(self.url(level) + '/mau', params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return load_workbook(BytesIO(response.content))

    def upload(self, level, values, edit=None):
        wb = self.template(level)
        ws = wb['CSVC']
        for row in ws.iter_rows(min_row=8):
            row[3].value = values.get(row[0].value)
        if edit:
            edit(ws)
        stream = BytesIO()
        wb.save(stream)
        response = self.client.post(self.url(level) + '/xem-truoc',
            data=dict(csrf=self.csrf, school_year_id=1, school_id=self.sid(level)), files={'excel_file':('CSVC.xlsx', stream.getvalue())})
        return response

    def confirm(self, level, preview):
        token = re.search(r'name="token" value="([^"]+)"', preview.text)[1]
        return self.client.post(self.url(level) + '/xac-nhan', data=dict(csrf=self.csrf, token=token, acknowledge='yes'), follow_redirects=False)

    def test_import_all_levels_same_storage_and_export(self):
        for level in ('MN', 'TH', 'THCS'):
            with self.subTest(level=level):
                values = {'facility_count':1, 'total_classroom_count':12} if level == 'MN' else {'class_total':10, 'room_permanent':12}
                preview = self.upload(level, values)
                self.assertEqual(preview.status_code, 200, preview.text)
                self.assertIsNone(service.current_record(self.db, level, 1, self.sid(level)), 'Preview writes no CSVC record')
                response = self.confirm(level, preview)
                self.assertEqual(response.status_code, 303, response.text)
                record = service.current_record(self.db, level, 1, self.sid(level))
                self.assertTrue(record)
                actual = service.saved_values(record, level)
                for code, value in values.items():
                    self.assertEqual(actual[code], value)
                manual = self.client.get(response.headers['location'])
                self.assertEqual(manual.status_code, 200, manual.text)
                self.assertIn('Nhập Excel CSVC', manual.text)
                if level != 'MN':
                    ws = Workbook().active
                    _structured_overlay_export(ws=ws, db=self.db, school_year_id=1, selected_commune_id=None,
                        selected_school_id=self.sid(level), level=level, form_code=service.catalog(level)['form_code'],
                        start_row=8, total_row=6, max_rows=100, meta={'kind':'school'}, aggregate_if_province=False)
                    fields = {f['code']:f for f in service.flatten_fields(service.catalog(level))}
                    self.assertEqual(ws.cell(8, fields['room_permanent']['excel_col']).value, 12)
                    self.assertEqual(ws.cell(8, service.catalog(level)['derived']['excel_col']).value, 1.2)

    def test_blank_preserves_zero_updates_and_other_records_unchanged(self):
        self.db.add_all([
            SchoolMn01CsvcInput(school_id=1, school_year_id=1, facility_count=4, kitchen_count=3, notes='Keep notes'),
            SchoolMn01CsvcInput(school_id=1, school_year_id=2, facility_count=9),
            SchoolStructuredReportInput(school_id=2, school_year_id=1, form_code='TH_01_CSVC', data_json=json.dumps({'room_permanent':4, 'library_room_area':25.5, 'future_field':42}), notes='Keep structure'),
            SchoolStructuredReportInput(school_id=2, school_year_id=1, form_code='TH_01_GV', data_json='{"teacher_total":55}'),
        ])
        self.db.commit()
        self.assertEqual(self.confirm('MN', self.upload('MN', {'facility_count':0})).status_code, 303)
        rec = service.current_record(self.db, 'MN', 1, 1)
        self.assertEqual((rec.facility_count, rec.kitchen_count, rec.notes), (0, 3, 'Keep notes'))
        self.assertEqual(service.current_record(self.db, 'MN', 2, 1).facility_count, 9)
        self.assertEqual(self.confirm('TH', self.upload('TH', {'room_permanent':0})).status_code, 303)
        rec = service.current_record(self.db, 'TH', 1, 2)
        self.assertEqual(json.loads(rec.data_json), {'room_permanent':0, 'library_room_area':25.5, 'future_field':42})
        self.assertEqual(rec.notes, 'Keep structure')
        self.assertEqual(inputs._structured_record(self.db, school_id=2, school_year_id=1, form_code='TH_01_GV').data_json, '{"teacher_total":55}')

    def test_decimal_and_yesno(self):
        fields = service.flatten_fields(service.catalog('TH'))
        flag = next(f['code'] for f in fields if f['type'] == 'yesno')
        preview = self.upload('TH', {'library_room_area':'12,75', flag:'Không'})
        self.assertEqual(self.confirm('TH', preview).status_code, 303)
        data = service.saved_values(service.current_record(self.db, 'TH', 1, 2), 'TH')
        self.assertEqual(data['library_room_area'], 12.75)
        self.assertEqual(data[flag], 0)

    def test_preschool_report_uses_imported_counts(self):
        preview = self.upload('MN', {'preschool_class_3_4_count':4, 'preschool_class_5_count':2,
            'permanent_preschool_room_count':6, 'equipped_preschool_class_count':6})
        self.assertEqual(self.confirm('MN', preview).status_code, 303)
        result = _b24311_load_mn02_csvc(self.db, {'selected_year_id':1, 'selected_school_id':1})
        self.assertTrue(result['has_csvc'])
        self.assertEqual(result['classes_total'], 6)
        self.assertEqual(result['preschool_rooms'], 6)
        self.assertEqual(result['room_ratio'], 1.0)
        self.assertEqual(result['equipped_5'], 2)

    def test_invalid_numbers_and_formula_block_entire_file(self):
        for bad in (-1, 1.5, 'NaN', 'Infinity', 'abc', '=2+2'):
            preview = self.upload('MN', {'facility_count':1, 'kitchen_count':bad})
            self.assertEqual(preview.status_code, 422, str(bad))
            self.assertNotIn('name="token"', preview.text)
            self.assertIsNone(service.current_record(self.db, 'MN', 1, 1))

    def test_wrong_scope_metadata_duplicate_and_blank(self):
        for cell in ('B2', 'B3', 'B4'):
            preview = self.upload('THCS', {'class_total':10}, edit=lambda ws: setattr(ws[cell], 'value', 'wrong'))
            self.assertEqual(preview.status_code, 422)
        preview = self.upload('THCS', {'class_total':10}, edit=lambda ws: ws.append([ws['A8'].value, ws['B8'].value, ws['C8'].value, 5]))
        self.assertEqual(preview.status_code, 422)
        self.assertEqual(self.upload('MN', {}).status_code, 422)

    def test_school_and_commune_scope(self):
        self.user = dict(id=1, role_code='TRUONG', school_id=3, commune_id=2)
        self.template('THCS')
        self.assertEqual(self.client.get(self.url('TH') + '?school_year_id=1&school_id=2').status_code, 403)
        self.assertEqual(self.client.get(self.url('MN') + '?school_year_id=1&school_id=3').status_code, 403)
        self.user = dict(id=1, role_code='XA', commune_id=1)
        self.template('MN')
        self.assertEqual(self.client.get(self.url('THCS') + '?school_year_id=1&school_id=3').status_code, 403)
        for role in ('GIAO_VIEN', 'PHONG_BAN'):
            self.user = dict(id=1, role_code=role, school_id=3, commune_id=2)
            self.assertEqual(self.client.get(self.url('THCS') + '?school_year_id=1&school_id=3').status_code, 403)
        self.assertTrue(AccessControlMiddleware._co_quyen_theo_thao_tac(path='/csvc/nhap-excel/THCS/xac-nhan', method='POST', role_code='TRUONG'))
        self.assertFalse(AccessControlMiddleware._co_quyen_theo_thao_tac(path='/csvc/nhap-excel/THCS/xac-nhan', method='POST', role_code='PHONG_BAN'))

    def test_csrf_replay_and_stale_preview(self):
        preview = self.upload('MN', {'facility_count':1})
        token = re.search(r'name="token" value="([^"]+)"', preview.text)[1]
        self.assertEqual(self.client.post(self.url('MN') + '/xac-nhan', data=dict(csrf='wrong', token=token, acknowledge='yes')).status_code, 403)
        self.assertEqual(self.confirm('MN', preview).status_code, 303)
        self.assertEqual(self.confirm('MN', preview).status_code, 409)
        preview = self.upload('MN', {'facility_count':2})
        rec = service.current_record(self.db, 'MN', 1, 1)
        rec.kitchen_count = 5
        self.db.commit()
        self.assertEqual(self.confirm('MN', preview).status_code, 409)
        self.db.refresh(rec)
        self.assertEqual(rec.facility_count, 1)

    def test_failed_save_rolls_back(self):
        preview = self.upload('THCS', {'class_total':10})
        original = service.store_patch
        def fail(*args):
            original(*args)
            raise RuntimeError('simulated failure')
        with patch.object(service, 'store_patch', side_effect=fail), self.assertLogs(route.logger, level='ERROR'):
            self.assertEqual(self.confirm('THCS', preview).status_code, 500)
        self.assertIsNone(service.current_record(self.db, 'THCS', 1, 3))


if __name__ == '__main__':
    unittest.main()
