import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.pipeline import execute,sample_bytes
@pytest.fixture
def dirty():return execute(sample_bytes())
@pytest.fixture
def clean():return execute(sample_bytes('clean'))
@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('DB_PATH',str(tmp_path/'cdr.sqlite3'))
    with TestClient(app) as c:yield c
