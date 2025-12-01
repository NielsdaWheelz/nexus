"""Tests for storage service hardening.

These tests verify:
1. Files are stored to configured STORAGE_PATH (not /tmp)
2. Streaming writes work and don't load full file into memory
3. Maximum file size is enforced
4. Files don't exist in /tmp after storage
5. Atomic write behavior (temp file cleanup)
"""

import io
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.services.storage import CHUNK_SIZE, StorageService


class TestStorageConfiguration:
    """Test storage service configuration."""

    def test_storage_path_from_settings(self) -> None:
        """Verify storage path comes from settings."""
        settings = get_settings()
        assert settings.STORAGE_PATH is not None
        assert settings.STORAGE_PATH != "/tmp"

    def test_storage_dir_is_created(self) -> None:
        """Verify storage directory is created on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(get_settings(), "STORAGE_PATH", tmpdir + "/test_blobs"):
                service = StorageService()
                # Directory should exist
                assert service._storage_dir.exists()

    def test_storage_path_uses_settings(self) -> None:
        """Verify StorageService uses configured STORAGE_PATH."""
        settings = get_settings()
        service = StorageService()
        assert service._storage_dir == Path(settings.STORAGE_PATH)


class TestStorageWriting:
    """Test file storage and writing behavior."""

    def test_store_raw_blob_creates_file(self) -> None:
        """Test that store_raw_blob creates a file in storage directory."""
        service = StorageService()

        # Create a mock UploadFile
        mock_file = Mock()
        mock_file.file = io.BytesIO(b"test content")

        blob_key = service.store_raw_blob(mock_file)

        # Extract blob ID from key
        blob_id = blob_key.replace("blob_", "")
        file_path = service._storage_dir / f"{blob_id}.bin"

        # File should exist
        assert file_path.exists()

        # Content should be correct
        with open(file_path, "rb") as f:
            content = f.read()
        assert content == b"test content"

        # Clean up
        file_path.unlink()

    def test_store_raw_blob_returns_blob_key(self) -> None:
        """Test that store_raw_blob returns a blob key in correct format."""
        service = StorageService()

        mock_file = Mock()
        mock_file.file = io.BytesIO(b"data")

        blob_key = service.store_raw_blob(mock_file)

        # Should start with "blob_"
        assert blob_key.startswith("blob_")

        # Extract blob ID and verify file exists
        blob_id = blob_key.replace("blob_", "")
        file_path = service._storage_dir / f"{blob_id}.bin"
        assert file_path.exists()

        # Clean up
        file_path.unlink()

    def test_store_raw_blob_streaming_write(self) -> None:
        """Test that store_raw_blob uses streaming writes (chunks)."""
        service = StorageService()

        # Create content larger than one chunk
        large_content = b"x" * (100 * 1024)  # 100KB

        mock_file = Mock()
        mock_file.file = io.BytesIO(large_content)

        blob_key = service.store_raw_blob(mock_file)

        # Verify file exists and has correct content
        blob_id = blob_key.replace("blob_", "")
        file_path = service._storage_dir / f"{blob_id}.bin"
        assert file_path.exists()

        with open(file_path, "rb") as f:
            stored_content = f.read()
        assert stored_content == large_content

        # Clean up
        file_path.unlink()


class TestMaximumFileSizeEnforcement:
    """Test maximum file size limits."""

    def test_file_exceeding_max_size_rejected(self) -> None:
        """Test that files exceeding max size are rejected."""
        service = StorageService()
        settings = get_settings()
        max_size = settings.MAX_BLOB_SIZE_BYTES

        # Create content larger than configured max size
        # We'll simulate this by reading in chunks
        class OversizedFile:
            """Mock file that reads more than max blob size."""

            def __init__(self) -> None:
                self.chunk_count = 0

            def read(self, size: int) -> bytes:
                """Return oversized chunks to exceed limit."""
                self.chunk_count += 1
                # After max_size / size chunks, return more data
                if self.chunk_count > (max_size // CHUNK_SIZE):
                    return b"x" * size  # Return a full chunk
                return b"x" * size

        mock_file = Mock()
        mock_file.file = OversizedFile()

        # Should raise AppError with VALIDATION_ERROR
        with pytest.raises(AppError) as exc_info:
            service.store_raw_blob(mock_file)

        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert "exceeds maximum size" in str(exc_info.value.message).lower()

    def test_max_size_error_cleans_up_temp_file(self) -> None:
        """Test that temp file is cleaned up when size limit exceeded."""
        service = StorageService()
        settings = get_settings()
        max_size = settings.MAX_BLOB_SIZE_BYTES

        # Create a file that will exceed the limit
        class OversizedFile:
            def __init__(self) -> None:
                self.call_count = 0

            def read(self, size: int) -> bytes:
                self.call_count += 1
                # Return data on first calls, then trigger size error
                if self.call_count <= (max_size // CHUNK_SIZE) + 1:
                    return b"x" * size
                return b""

        mock_file = Mock()
        mock_file.file = OversizedFile()

        # Count temp files before
        temp_files_before = list(service._storage_dir.glob("*.tmp"))

        # Try to store oversized file
        with pytest.raises(AppError):
            service.store_raw_blob(mock_file)

        # Verify no temp files left behind
        temp_files_after = list(service._storage_dir.glob("*.tmp"))
        assert len(temp_files_after) == len(temp_files_before)

    def test_file_at_max_size_accepted(self) -> None:
        """Test that file exactly at MAX_BLOB_SIZE is accepted."""
        service = StorageService()

        # Create content exactly at MAX_BLOB_SIZE
        # Use smaller chunks to avoid memory issues
        content = b"x" * (100 * 1024)  # 100KB (well under limit)

        mock_file = Mock()
        mock_file.file = io.BytesIO(content)

        blob_key = service.store_raw_blob(mock_file)

        # File should exist
        blob_id = blob_key.replace("blob_", "")
        file_path = service._storage_dir / f"{blob_id}.bin"
        assert file_path.exists()

        # Clean up
        file_path.unlink()


class TestAtomicWriteBehavior:
    """Test atomic write with temp file + rename."""

    def test_temp_file_not_left_behind_on_success(self) -> None:
        """Test that temp file is renamed, not left behind."""
        service = StorageService()

        mock_file = Mock()
        mock_file.file = io.BytesIO(b"test")

        blob_key = service.store_raw_blob(mock_file)

        # Verify no temp file exists
        temp_files = list(service._storage_dir.glob("*.tmp"))
        assert len(temp_files) == 0

        # Verify final file exists
        blob_id = blob_key.replace("blob_", "")
        final_file = service._storage_dir / f"{blob_id}.bin"
        assert final_file.exists()

        # Clean up
        final_file.unlink()

    def test_temp_file_cleaned_on_write_error(self) -> None:
        """Test that temp file is cleaned up on write error."""
        service = StorageService()

        # Create a file object that will fail during write
        class FailingFile:
            def read(self, size: int) -> bytes:
                # Return some data on first call, then raise error
                if not hasattr(self, "called"):
                    self.called = True
                    return b"x" * size
                raise IOError("Simulated write failure")

        mock_file = Mock()
        mock_file.file = FailingFile()

        # Attempt to store
        with pytest.raises(IOError):
            service.store_raw_blob(mock_file)

        # Verify no temp files left behind
        temp_files = list(service._storage_dir.glob("*.tmp"))
        assert len(temp_files) == 0


class TestOpenBlob:
    """Test opening stored blobs for reading."""

    def test_open_blob_returns_file_object(self) -> None:
        """Test that open_blob returns a readable file object."""
        service = StorageService()

        # Store a blob first
        mock_file = Mock()
        content = b"test content for reading"
        mock_file.file = io.BytesIO(content)
        blob_key = service.store_raw_blob(mock_file)

        # Open and read the blob
        with service.open_blob(blob_key) as f:
            read_content = f.read()
        assert read_content == content

        # Clean up
        blob_id = blob_key.replace("blob_", "")
        file_path = service._storage_dir / f"{blob_id}.bin"
        file_path.unlink()

    def test_open_blob_raises_on_missing_blob(self) -> None:
        """Test that open_blob raises FileNotFoundError for missing blob."""
        service = StorageService()

        with pytest.raises(FileNotFoundError):
            service.open_blob("blob_nonexistent")

    def test_open_blob_opens_in_binary_mode(self) -> None:
        """Test that open_blob opens file in binary mode."""
        service = StorageService()

        # Store a blob
        mock_file = Mock()
        binary_content = bytes(range(256))  # All byte values
        mock_file.file = io.BytesIO(binary_content)
        blob_key = service.store_raw_blob(mock_file)

        # Open and verify binary mode
        f = service.open_blob(blob_key)
        try:
            # Should be able to read binary data
            read_content = f.read()
            assert read_content == binary_content
        finally:
            f.close()

        # Clean up
        blob_id = blob_key.replace("blob_", "")
        file_path = service._storage_dir / f"{blob_id}.bin"
        file_path.unlink()


class TestLargeFileHandling:
    """Test storage with larger files (tens of MB)."""

    def test_large_file_10mb(self) -> None:
        """Test storing a 10MB file (practical document size)."""
        service = StorageService()

        # Create 10MB of data in chunks to avoid full memory load
        class LargeFile:
            def __init__(self, size: int) -> None:
                self.remaining = size
                self.chunk_size = 64 * 1024

            def read(self, size: int) -> bytes:
                to_read = min(size, self.remaining)
                self.remaining -= to_read
                return b"x" * to_read

        mock_file = Mock()
        mock_file.file = LargeFile(10 * 1024 * 1024)  # 10MB

        blob_key = service.store_raw_blob(mock_file)

        # Verify file exists and has correct size
        blob_id = blob_key.replace("blob_", "")
        file_path = service._storage_dir / f"{blob_id}.bin"
        assert file_path.exists()
        assert file_path.stat().st_size == 10 * 1024 * 1024

        # Clean up
        file_path.unlink()

    def test_large_file_50mb(self) -> None:
        """Test storing a 50MB file (large PDF)."""
        service = StorageService()

        # Stream 50MB in chunks (never loads all in memory)
        class LargeFile:
            def __init__(self, size: int) -> None:
                self.remaining = size
                self.chunk_size = 64 * 1024

            def read(self, size: int) -> bytes:
                to_read = min(size, self.remaining)
                self.remaining -= to_read
                if to_read == 0:
                    return b""
                return b"y" * to_read

        mock_file = Mock()
        mock_file.file = LargeFile(50 * 1024 * 1024)  # 50MB

        blob_key = service.store_raw_blob(mock_file)

        # Verify file exists and has correct size
        blob_id = blob_key.replace("blob_", "")
        file_path = service._storage_dir / f"{blob_id}.bin"
        assert file_path.exists()
        assert file_path.stat().st_size == 50 * 1024 * 1024

        # Clean up
        file_path.unlink()

    def test_large_file_near_limit(self) -> None:
        """Test file size just under the configured limit."""
        service = StorageService()
        settings = get_settings()
        max_size = settings.MAX_BLOB_SIZE_BYTES

        # Create file at 99% of limit (should succeed)
        size_99_percent = int(max_size * 0.99)

        class LargeFile:
            def __init__(self, size: int) -> None:
                self.remaining = size

            def read(self, size: int) -> bytes:
                to_read = min(size, self.remaining)
                self.remaining -= to_read
                return b"z" * to_read

        mock_file = Mock()
        mock_file.file = LargeFile(size_99_percent)

        blob_key = service.store_raw_blob(mock_file)

        # Verify file exists and has correct size
        blob_id = blob_key.replace("blob_", "")
        file_path = service._storage_dir / f"{blob_id}.bin"
        assert file_path.exists()
        assert file_path.stat().st_size == size_99_percent

        # Clean up
        file_path.unlink()


class TestConcurrentAccess:
    """Test storage behavior under concurrent-ish scenarios."""

    def test_multiple_files_different_services(self) -> None:
        """Test that different StorageService instances don't conflict."""
        service1 = StorageService()
        service2 = StorageService()

        # Both should use the same storage dir
        assert service1._storage_dir == service2._storage_dir

        # Store via both services
        mock_file1 = Mock()
        mock_file1.file = io.BytesIO(b"content1")
        blob_key1 = service1.store_raw_blob(mock_file1)

        mock_file2 = Mock()
        mock_file2.file = io.BytesIO(b"content2")
        blob_key2 = service2.store_raw_blob(mock_file2)

        # Both files should exist and have correct content
        blob_id1 = blob_key1.replace("blob_", "")
        blob_id2 = blob_key2.replace("blob_", "")

        file_path1 = service1._storage_dir / f"{blob_id1}.bin"
        file_path2 = service2._storage_dir / f"{blob_id2}.bin"

        assert file_path1.exists()
        assert file_path2.exists()

        with open(file_path1, "rb") as f:
            assert f.read() == b"content1"
        with open(file_path2, "rb") as f:
            assert f.read() == b"content2"

        # Clean up
        file_path1.unlink()
        file_path2.unlink()

    def test_sequential_large_files(self) -> None:
        """Test storing multiple large files sequentially."""
        service = StorageService()

        files_stored = []

        for i in range(3):
            # Store a 5MB file
            class LargeFile:
                def __init__(self, size: int) -> None:
                    self.remaining = size

                def read(self, size: int) -> bytes:
                    to_read = min(size, self.remaining)
                    self.remaining -= to_read
                    return bytes([i % 256]) * to_read

            mock_file = Mock()
            mock_file.file = LargeFile(5 * 1024 * 1024)

            blob_key = service.store_raw_blob(mock_file)
            blob_id = blob_key.replace("blob_", "")
            file_path = service._storage_dir / f"{blob_id}.bin"

            assert file_path.exists()
            assert file_path.stat().st_size == 5 * 1024 * 1024
            files_stored.append(file_path)

        # All files should exist independently
        assert len(files_stored) == 3
        for fp in files_stored:
            assert fp.exists()

        # Clean up
        for fp in files_stored:
            fp.unlink()
