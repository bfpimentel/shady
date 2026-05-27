import json
import tempfile
import unittest
from pathlib import Path

import app


class ShadyTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.dynamic_file = root / "dynamic.json"
        self.mock_file = root / "mocks.json"

        self.previous_dynamic_file = app.DYNAMIC_FILE
        self.previous_mock_file = app.MOCK_FILE
        self.previous_upload_folder = app.UPLOAD_FOLDER
        self.previous_use_mocks = app.USE_MOCKS
        self.previous_dynamic_entries = app.dynamic_entries_list

        app.DYNAMIC_FILE = str(self.dynamic_file)
        app.MOCK_FILE = str(self.mock_file)
        app.UPLOAD_FOLDER = str(root / "uploads")
        app.USE_MOCKS = False
        app.dynamic_entries_list = []
        Path(app.UPLOAD_FOLDER).mkdir()
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()

    def tearDown(self):
        app.DYNAMIC_FILE = self.previous_dynamic_file
        app.MOCK_FILE = self.previous_mock_file
        app.UPLOAD_FOLDER = self.previous_upload_folder
        app.USE_MOCKS = self.previous_use_mocks
        app.dynamic_entries_list = self.previous_dynamic_entries
        self.tmp.cleanup()

    def test_validates_dynamic_urls(self):
        response = self.client.post("/dynamic", data={"name": "bad", "url": "ftp://example.com"})
        self.assertEqual(response.status_code, 400)

    def test_adds_and_deletes_dynamic_entry(self):
        response = self.client.post("/dynamic", data={"name": "docs", "url": "https://example.com"})
        self.assertEqual(response.status_code, 302)

        app.scan_dynamic_entries()
        self.assertEqual(app.dynamic_entries_list, [{"name": "docs", "url": "https://example.com"}])

        response = self.client.post("/dynamic/docs")
        self.assertEqual(response.status_code, 302)

        app.scan_dynamic_entries()
        self.assertEqual(app.dynamic_entries_list, [])

    def test_loads_mock_entries_sorted(self):
        self.mock_file.write_text(
            json.dumps({"containers": [{"name": "z", "url": "https://z.test"}, {"name": "a", "url": "https://a.test"}]}),
            encoding="utf-8",
        )

        self.assertEqual(
            app.load_mock_entries("containers"),
            [{"name": "a", "url": "https://a.test"}, {"name": "z", "url": "https://z.test"}],
        )

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"])

    def test_serves_uploaded_folder_assets_and_pages(self):
        site = Path(app.UPLOAD_FOLDER) / "site"
        nested = site / "nested"
        nested.mkdir(parents=True)
        (site / "index.html").write_text('<img src="header.jpeg">', encoding="utf-8")
        (site / "header.jpeg").write_bytes(b"fake image")
        (site / "about.html").write_text("about", encoding="utf-8")
        (nested / "index.html").write_text("nested", encoding="utf-8")

        self.assertEqual(self.client.get("/site/").status_code, 200)
        self.assertEqual(self.client.get("/site/header.jpeg").data, b"fake image")
        self.assertEqual(self.client.get("/site/about").data, b"about")
        self.assertEqual(self.client.get("/site/nested/").data, b"nested")
        self.assertEqual(self.client.get("/site/../dynamic.json").status_code, 404)


if __name__ == "__main__":
    unittest.main()
