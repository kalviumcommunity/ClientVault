"""Tests for document upload & indexing endpoint (src/document_upload.py)."""
import io
import json
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi import FastAPI

# Need to wire the router into an app
from src.document_upload import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


class TestValidation(unittest.TestCase):
    def test_no_file(self):
        resp = client.post("/documents")
        self.assertEqual(resp.status_code, 422)

    def test_unsupported_extension(self):
        resp = client.post("/documents",
                           files={"file": ("test.exe", b"content", "application/octet-stream")})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("unsupported", resp.json()["detail"].lower())

    def test_empty_file(self):
        resp = client.post("/documents",
                           files={"file": ("empty.md", b"", "text/markdown")})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("empty", resp.json()["detail"].lower())

    def test_unsafe_filename(self):
        resp = client.post("/documents",
                           files={"file": ("../../../etc/passwd", b"content", "text/plain")})
        self.assertEqual(resp.status_code, 400)


class TestUploadAndIndex(unittest.TestCase):
    def test_upload_markdown(self):
        content = b"# Test Document\n\nClient ID: ACME-001\n\nThis is test content for upload indexing."
        resp = client.post("/documents",
                           files={"file": ("test_upload.md", content, "text/markdown")})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(data["status"], ("indexed", "partial"))

    def test_upload_txt(self):
        content = b"Client ID: NEXUS-002\n\nSimple text document for testing."
        resp = client.post("/documents",
                           files={"file": ("test_doc.txt", content, "text/plain")})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("document_id", data)
        self.assertGreaterEqual(data["chunks_created"], 0)

    def test_response_shape(self):
        content = b"# Test\nClient ID: TEST-001\n\nBody content."
        resp = client.post("/documents",
                           files={"file": ("shape_test.md", content, "text/markdown")})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("filename", data)
        self.assertIn("chunks_created", data)
        self.assertIn("chunks_indexed", data)
        self.assertIn("errors", data)


if __name__ == "__main__":
    unittest.main()
