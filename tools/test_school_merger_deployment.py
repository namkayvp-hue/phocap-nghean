import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.services import school_merger_official_registry as registry
from app.routers import school_merger as router


class MergerDeploymentTests(unittest.TestCase):
    def test_missing_server_registry_uses_bundled_plans_and_level_locks(self):
        with patch.object(registry, 'REGISTRY_FILE', Path('missing-data/registry.json').with_name('school_merger_official_registry.json')), \
             patch.object(registry, 'LEVEL_LOCK_FILE', Path('missing-data/qd3805_level_lock.json')):
            self.assertGreater(registry.official_registry_summary()['group_count'], 0)
            self.assertTrue(registry._load_level_lock_index())
            self.assertTrue(registry._load_mn_action_lock_operations())

    def test_existing_invalid_server_registry_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'school_merger_official_registry.json'
            path.write_text('{}', encoding='utf-8')
            with patch.object(registry, 'REGISTRY_FILE', path):
                with self.assertRaises(registry.SchoolMergerRegistryError):
                    registry._load_registry()
            path.write_text(json.dumps({'plans':[], 'school_year_code':'custom'}), encoding='utf-8')
            with patch.object(registry, 'REGISTRY_FILE', path):
                self.assertEqual(registry.official_registry_summary()['school_year_code'], 'custom')

    def test_page_displays_registry_error_without_internal_server_error(self):
        app = FastAPI()
        @app.middleware('http')
        async def auth(request, call_next):
            request.scope['auth_user'] = {'role_code':'ADMIN'}
            return await call_next(request)
        app.include_router(router.router)
        with patch.object(router,'list_school_years',return_value=[]), \
             patch.object(router,'list_communes',return_value=[]), \
             patch.object(router,'merger_history',return_value=[]), \
             patch.object(router,'official_registry_summary',side_effect=registry.SchoolMergerRegistryError('Thiếu sổ phương án')):
            with TestClient(app) as client:
                response = client.get('/cong-cu-du-lieu/sap-nhap-truong')
            self.assertEqual(response.status_code,200)
            self.assertIn('Thiếu sổ phương án',response.text)


if __name__ == '__main__':
    unittest.main()
