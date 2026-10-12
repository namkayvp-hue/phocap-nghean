"""Regression checks without reading or writing the production database."""
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

from starlette.requests import Request

from app.access_control import AccessControlMiddleware as Access
from app.routers.communes import danh_sach_xa


class DepartmentAccessTests(unittest.TestCase):
    def test_read_and_export(self):
        for path in ("/xa", "/xa/", "/bao-cao", "/bao-cao/xuat-excel",
                     "/dieu-tra/1/ho-dan", "/dieu-tra/2/xuat-excel"):
            with self.subTest(path=path):
                self.assertTrue(Access._co_quyen_theo_vai_tro(path=path, role_code="PHONG_BAN"))
                self.assertTrue(Access._co_quyen_theo_thao_tac(path=path, method="GET", role_code="PHONG_BAN"))

    def test_block_direct_writes(self):
        for path in ("/xa/them", "/xa/1/sua", "/xa/1/khoa-mo",
                     "/dieu-tra/1/khoa-xa", "/doi-ngu/them",
                     "/bao-cao/tai-chinh/nhap", "/bieu-nhap/th-01-gv"):
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                with self.subTest(path=path, method=method):
                    self.assertFalse(Access._co_quyen_theo_thao_tac(path=path, method=method, role_code="PHONG_BAN"))
        self.assertFalse(Access._co_quyen_theo_thao_tac(path="/xa/1/sua", method="GET", role_code="PHONG_BAN"))
        self.assertTrue(Access._co_quyen_theo_thao_tac(path="/dang-xuat", method="POST", role_code="PHONG_BAN"))
        self.assertTrue(Access._co_quyen_theo_thao_tac(path="/xa/them", method="POST", role_code="ADMIN"))

    def test_all_communes_render_read_only(self):
        rows = [SimpleNamespace(id=i, code=f"XA{i}", name=f"Commune {i}",
                is_active=True, is_special_difficulty_area=False, created_at=datetime(2026, 1, 1))
                for i in (1, 2)]
        db = Mock()
        db.scalars.return_value.all.return_value = rows
        for role in ("PHONG_BAN", "ADMIN"):
            request = Request({"type": "http", "method": "GET", "path": "/xa",
                               "headers": [], "auth_user": {"role_code": role}})
            response = danh_sach_xa(request=request, db=db)
            html = response.body.decode()
            for row in rows:
                self.assertIn(row.name, html)
            for action in ('action="/xa/them"', 'href="/xa/1/sua"', '/xa/1/khoa-mo'):
                if role == "PHONG_BAN":
                    self.assertNotIn(action, html)
                else:
                    self.assertIn(action, html)


if __name__ == "__main__":
    unittest.main()
