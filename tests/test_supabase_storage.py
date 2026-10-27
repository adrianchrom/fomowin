import unittest
from unittest.mock import patch, MagicMock
from monitors.supabase_storage import SupabaseStorage


class TestSupabaseStorage(unittest.TestCase):
    def test_disabled_by_default_without_env(self):
        storage = SupabaseStorage()
        storage.url = ""
        storage.key = ""
        self.assertFalse(storage.is_enabled())
        self.assertIsNone(storage.fetch_key("test"))
        self.assertFalse(storage.save_key("test", {"a": 1}))

    @patch("requests.get")
    def test_fetch_key_success(self, mock_get):
        storage = SupabaseStorage()
        storage.url = "https://example.supabase.co"
        storage.key = "fake-key"
        self.assertTrue(storage.is_enabled())

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"key": "DATA_WYDATKI", "data": {"test": 123}}]
        mock_get.return_value = mock_resp

        val = storage.fetch_key("DATA_WYDATKI")
        self.assertEqual(val, {"test": 123})
        mock_get.assert_called_once()

    @patch("requests.post")
    def test_save_key_success(self, mock_post):
        storage = SupabaseStorage()
        storage.url = "https://example.supabase.co"
        storage.key = "fake-key"

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_post.return_value = mock_resp

        res = storage.save_key("DATA_WYDATKI", {"hello": "world"})
        self.assertTrue(res)
        mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
