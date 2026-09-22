import os
os.environ["DATABASE_URL"] = "sqlite:///./test_content_engine.db"
os.environ["OUTPUT_DIR"] = "./test_output"
os.environ["ALLOW_DEMO_FALLBACK"] = "true"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ELEVENLABS_API_KEY"] = ""
os.environ["ELEVENLABS_VOICE_ID"] = ""
os.environ["ENGINE_API_TOKEN"] = ""

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
