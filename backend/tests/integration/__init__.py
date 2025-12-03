"""Integration tests requiring real Celery workers and Redis.

These tests are marked with @pytest.mark.integration and require:
- Test database running (test-db)
- Test Redis running (test-redis)
- Test Celery worker running (test-worker)

Run with: make backend-test-integration
"""

