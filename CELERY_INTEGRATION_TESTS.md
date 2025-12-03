# Celery Integration Tests - Spec

## The Problem

The failing test `test_chunk_document_task_propagates_errors` tries to call a Celery task directly without providing a database session. The task creates its own session via production config, which fails in test environments.

More broadly: We can't test the real task pipeline (ingest→chunk→embed) because `task_always_eager=True` hides concurrency bugs:
1. **Race condition**: Document flushed but not committed when task enqueues → downstream task sees stale data
2. **Silent failures**: If embedding validation fails, document status isn't updated
3. **Lock behavior**: PostgreSQL locks never tested with concurrent workers
4. **Retry misconfiguration**: ValidationErrors are retried when they shouldn't be

## The Solution

Add real Celery + Redis integration tests that:
- Run full pipeline with actual workers
- Detect race conditions between flush and task enqueue
- Test retry behavior and locking with real concurrency

Keep unit tests unchanged (auto-enable `task_always_eager=True` via fixture).

## What Gets Built

### Docker (docker-compose.yml)
Add 2 services on `test` profile:
- `test-redis`: Redis on port 6380, database 1 (separate from dev Redis)
- `test-worker`: Celery worker connected to test Redis + test DB

### Code (backend/tests/)
- `celery_config.py`: Fixtures for eager (unit) and real (integration) Celery modes
- `integration/conftest.py`: Polling helpers for async testing
- `integration/test_pipeline_full.py`: 2 tests—full pipeline + durability check

### Config
- `conftest.py`: Add `celery_eager_for_unit_tests` autouse fixture
- `pyproject.toml`: Add `@pytest.mark.integration` marker
- `Makefile` (root + backend): Add test targets

## Implementation (2-3 hours)

**Phase 1: Docker (30 min)**
```yaml
# Add to docker-compose.yml under test profile
test-redis:
  image: redis:7-alpine
  container_name: nexus-test-redis
  ports: ["6380:6379"]
  profiles: [test]
  networks: [nexus]

test-worker:
  build: ../backend
  container_name: nexus-test-worker
  command: celery -A app.celery_app worker -Q documents,embeddings -l info
  depends_on: [test-redis, test-db]
  environment:
    - DATABASE_URL=postgresql+psycopg://app_user:password@test-db:5432/test_nexus
    - REDIS_URL=redis://test-redis:6379/1
  profiles: [test]
  networks: [nexus]
```

Add to Makefile:
```makefile
test-infra-up:
	docker compose -f infra/docker-compose.yml --profile test up -d test-db test-redis test-worker

test-infra-down:
	docker compose -f infra/docker-compose.yml --profile test down

backend-test-integration: test-infra-up
	cd backend && DATABASE_URL=postgresql+psycopg://app_user:password@localhost:5433/test_nexus \
	              REDIS_URL=redis://localhost:6380/1 \
	              make test-integration && \
	docker compose -f infra/docker-compose.yml --profile test down
```

**Phase 2: Celery config (30 min)**

Create `backend/tests/celery_config.py`:
```python
import os
import pytest
from redis import Redis
from app.celery_app import celery_app

@pytest.fixture
def celery_app_eager():
    """Sync execution for unit tests."""
    app = celery_app
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    yield app
    app.conf.task_always_eager = False
    app.conf.task_eager_propagates = False

@pytest.fixture
def celery_app_real():
    """Real async execution with test Redis."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        pytest.skip("REDIS_URL not set")

    try:
        Redis.from_url(redis_test_url).ping()
    except Exception as e:
        pytest.skip(f"Cannot connect to test Redis: {e}")

    app = celery_app
    original_broker = app.conf.broker_url
    original_backend = app.conf.result_backend

    app.conf.broker_url = redis_test_url
    app.conf.result_backend = redis_test_url
    app.conf.task_always_eager = False

    yield app

    app.conf.broker_url = original_broker
    app.conf.result_backend = original_backend

@pytest.fixture
def redis_test():
    """Redis client for test inspection."""
    url = os.getenv("REDIS_URL")
    if not url:
        pytest.skip("REDIS_URL not set")
    client = Redis.from_url(url, decode_responses=True)
    yield client
    client.flushdb()
    client.close()
```

Update `backend/tests/conftest.py` (add):
```python
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "integration: real Celery/Redis tests")

@pytest.fixture(autouse=True)
def celery_eager_for_unit_tests(request):
    """Auto-enable eager mode for unit tests."""
    if "integration" not in request.keywords:
        from app.celery_app import celery_app
        celery_app.conf.task_always_eager = True
        celery_app.conf.task_eager_propagates = True
        yield
        celery_app.conf.task_always_eager = False
        celery_app.conf.task_eager_propagates = False
    else:
        yield
```

Update `backend/pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = [
    "integration: integration tests requiring real Celery/Redis",
]
```

Add to `backend/Makefile`:
```makefile
test-unit:
	$(PYTHON) -m pytest -m "not integration" --cov=app

test-integration:
	$(PYTHON) -m pytest tests/integration -m integration -v

test-all:
	$(PYTHON) -m pytest --cov=app

test: test-all
```

**Phase 3: Integration tests (1-2 hours)**

Create `backend/tests/integration/__init__.py` (empty).

Create `backend/tests/integration/conftest.py`:
```python
import time
from typing import Any
import pytest
from celery.result import AsyncResult
from redis import Redis

@pytest.fixture
def celery_integration_app(celery_app_real):
    return celery_app_real

@pytest.fixture
def redis_integration(redis_test):
    return redis_test

def wait_for_task(task_id: str, timeout: int = 30) -> Any:
    """Poll result backend until task completes."""
    result = AsyncResult(task_id)
    start = time.time()
    while time.time() - start < timeout:
        if result.ready():
            if result.successful():
                return result.result
            else:
                raise Exception(f"Task {task_id} failed: {result.info}")
        time.sleep(0.1)
    raise TimeoutError(f"Task {task_id} did not complete within {timeout}s")

@pytest.fixture
def wait_for_task_fixture():
    return wait_for_task

@pytest.fixture
def clear_queues(redis_integration):
    """Clear queues before/after test."""
    for queue in ["documents", "embeddings"]:
        redis_integration.delete(queue)
    yield
    for queue in ["documents", "embeddings"]:
        redis_integration.delete(queue)
```

Create `backend/tests/integration/test_pipeline_full.py`:
```python
import hashlib
import time
import uuid as uuid_lib
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.models.chunk import ContentChunk
from app.models.document import Document
from app.tasks.documents import ingest_document


@pytest.mark.integration
class TestFullPipeline:
    """Test complete ingest→chunk→embed pipeline with real workers."""

    def test_full_pipeline_end_to_end(
        self,
        db_session: Session,
        test_user,
        celery_integration_app,
        wait_for_task_fixture,
        clear_queues,
    ):
        """
        Verify full pipeline: ingestion→chunking→embedding.

        Tests:
        - ingest_document enqueues chunk_document
        - chunk_document enqueues embed_document
        - All tasks execute and update database
        """
        doc_id = uuid_lib.uuid4()
        canonical_text = "Para one.\n\nPara two.\n\nPara three."
        canonical_hash = hashlib.sha256(canonical_text.encode()).hexdigest()

        doc = Document(
            id=doc_id,
            user_id=test_user.id,
            title="Test",
            original_blob_key="key",
            original_mime_type="text/html",
            original_size_bytes=100,
            content_hash="hash",
            status="pending",
            embedding_status="pending",
        )
        db_session.add(doc)
        db_session.commit()

        with patch("app.services.ingestion.canonicalize_document") as mock_canon:
            mock_canon.return_value = type("obj", (object,), {
                "canonical_text": canonical_text,
                "canonical_hash": canonical_hash,
                "content_hash": "hash",
                "structure": None,
                "language": "en",
                "extractor_version": "html-v1",
                "text_byte_length": len(canonical_text.encode()),
            })()

            with patch("app.services.embeddings.embed_texts_with_default_client") as mock_embed:
                mock_embed.return_value = [[0.1] * 1536] * 3

                # Enqueue ingest task
                result = ingest_document.delay(str(doc_id))
                wait_for_task_fixture(result.id, timeout=30)

                # Give worker time to process downstream tasks
                time.sleep(2)

                # Verify document state
                db_session.expire_all()
                doc = db_session.query(Document).filter(Document.id == doc_id).one()
                assert doc.status == "ready"
                assert doc.canonical_text == canonical_text

                # Verify chunks created
                chunks = db_session.query(ContentChunk).filter(
                    ContentChunk.media_id == doc_id
                ).all()
                assert len(chunks) > 0

                # Verify chunks embedded
                embedded = [c for c in chunks if c.embedding is not None]
                assert len(embedded) > 0

    def test_chunks_durable_before_embedding(
        self,
        db_session: Session,
        test_user,
        celery_integration_app,
        wait_for_task_fixture,
        clear_queues,
    ):
        """
        Critical test: Chunks must be durable before embed_document dequeues.

        This catches race condition where:
        - chunk_document flushes chunks but transaction not committed
        - embed_document dequeues immediately, doesn't see chunks
        - Result: ValidationError "No chunks found"
        """
        doc_id = uuid_lib.uuid4()
        canonical_text = "Para one.\n\nPara two."
        canonical_hash = hashlib.sha256(canonical_text.encode()).hexdigest()

        doc = Document(
            id=doc_id,
            user_id=test_user.id,
            title="Test",
            original_blob_key="key",
            original_mime_type="text/html",
            original_size_bytes=100,
            content_hash="hash",
            status="pending",
            embedding_status="pending",
        )
        db_session.add(doc)
        db_session.commit()

        with patch("app.services.ingestion.canonicalize_document") as mock_canon:
            mock_canon.return_value = type("obj", (object,), {
                "canonical_text": canonical_text,
                "canonical_hash": canonical_hash,
                "content_hash": "hash",
                "structure": None,
                "language": "en",
                "extractor_version": "html-v1",
                "text_byte_length": len(canonical_text.encode()),
            })()

            with patch("app.services.embeddings.embed_texts_with_default_client") as mock_embed:
                mock_embed.return_value = [[0.1] * 1536] * 2

                # Enqueue full pipeline
                result = ingest_document.delay(str(doc_id))
                wait_for_task_fixture(result.id, timeout=30)
                time.sleep(3)

                # If race condition exists, embed_document will fail with
                # ValidationError "No chunks found" and chunks will be empty.
                # If fixed, chunks will be embedded.
                db_session.expire_all()
                chunks = db_session.query(ContentChunk).filter(
                    ContentChunk.media_id == doc_id
                ).all()

                embedded_count = sum(1 for c in chunks if c.embedding is not None)
                assert embedded_count > 0, (
                    "If this fails: race condition detected. "
                    "Chunks not durable before embed task dequeued."
                )
```

## Success Criteria

- ✓ Unit tests pass unchanged (`make backend-test`)
- ✓ Integration tests run with real workers (`make backend-test-integration`)
- ✓ Can detect race condition if it exists (durability test fails)
- ✓ Backward compatible (no changes to production code)

## Timeline

Total: **2-3 hours**
- Phase 1 (Docker): 30 min
- Phase 2 (Celery config): 30 min
- Phase 3 (Integration tests): 1-2 hours

Can be done in one focused session.

## When to Run

```bash
# Unit tests (no infrastructure needed)
make backend-test

# Integration tests (requires Docker + test services)
make backend-test-integration

# Both
make backend-test-all
```

Integration tests are optional in CI/CD until needed in production workflow.
