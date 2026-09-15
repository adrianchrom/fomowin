import unittest
from fastapi.testclient import TestClient
from main import app, auth_manager

class TestNewModules(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        token = "test_token_adrian"
        auth_manager.active_sessions[token] = "Adrian"
        self.client.cookies.set("fomo_session", token)

    def test_crm_crud(self):
        # 1. GET initial CRM list
        res = self.client.get('/api/crm')
        self.assertEqual(res.status_code, 200)

        # 2. Add client
        payload = {
            "name": "Firma Testowa",
            "company": "TestCorp",
            "email": "test@testcorp.com",
            "phone": "+48 500 100 200",
            "status": "Zainteresowany",
            "value": 5000,
            "notes": "Zapytanie o ofertę"
        }
        res = self.client.post('/api/crm', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        created_client = data.get("client")
        self.assertEqual(created_client["name"], "Firma Testowa")

        # 3. Update client
        update_payload = {**created_client, "status": "W trakcie negocjacji", "value": 7500}
        res = self.client.put(f"/api/crm/{created_client['id']}", json=update_payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("success"))

        # 4. Delete client
        res = self.client.delete(f"/api/crm/{created_client['id']}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("success"))

    def test_tasks_crud(self):
        # 1. GET initial tasks
        res = self.client.get('/api/tasks')
        self.assertEqual(res.status_code, 200)

        # 2. Add task
        payload = {
            "title": "Zadanie Testowe",
            "description": "Opis testowego zadania",
            "status": "todo",
            "priority": "Wysoki",
            "due_date": "2026-10-01"
        }
        res = self.client.post('/api/tasks', json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        created_task = data.get("task")
        self.assertEqual(created_task["title"], "Zadanie Testowe")

        # 3. Move task to in_progress
        update_payload = {**created_task, "status": "in_progress"}
        res = self.client.put(f"/api/tasks/{created_task['id']}", json=update_payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("success"))

        # 4. Delete task
        res = self.client.delete(f"/api/tasks/{created_task['id']}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get("success"))

    def test_currency_rates(self):
        res = self.client.get('/api/currency/rates')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn('rates', data)
        self.assertIn('EUR', data['rates'])
        self.assertIn('USD', data['rates'])

if __name__ == '__main__':
    unittest.main()
