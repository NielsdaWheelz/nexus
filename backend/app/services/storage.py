"""Storage service for managing document blobs.

PR 6.0 Implementation:
- Stores uploaded files to configurable storage path (hardened)
- Streams file writes in chunks (not full-memory reads)
- Enforces maximum file size limits
- Uses atomic write behavior (temp file + rename)
- Returns blob_key for database persistence

This implementation is production-hardened for PR 6.0.
Phase 2+ will add S3 integration and content-addressable storage.

Spec reference:
- PR 6.0: Storage Hardening
"""

import uuid
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode

# Streaming chunk size for writes (64KB is a good balance for most systems)
CHUNK_SIZE = 64 * 1024  # 64KB chunks for streaming


class StorageService:
    """Production-hardened storage service.

    Stores uploaded files with:
    - Configurable storage path from settings
    - Streaming writes (64KB chunks, not full-memory reads)
    - Maximum size enforcement
    - Atomic write behavior (temp file + rename)

    Note: This is local filesystem storage for Phase 1/Phase 2.
    Phase 3+ will support S3 and cloud storage backends.
    """

    def __init__(self) -> None:
        """Initialize storage service with configurable path and size limit."""
        settings = get_settings()
        self._storage_dir = Path(settings.STORAGE_PATH)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._max_blob_size = settings.MAX_BLOB_SIZE_BYTES

    def store_raw_blob(self, file: UploadFile) -> str:
        """Store uploaded file and return blob_key.

        Implementation:
        - Streams file in 64KB chunks (not full-memory read)
        - Enforces MAX_BLOB_SIZE_BYTES limit from settings
        - Uses atomic write: temp file → rename on completion
        - Returns blob_key = "blob_<uuid>"

        Args:
            file: UploadFile from FastAPI

        Returns:
            blob_key: Opaque string for database persistence (format: "blob_<uuid>")

        Raises:
            AppError: If file exceeds size limit (VALIDATION_ERROR)
            OSError: If file cannot be written (e.g., disk full)
            IOError: If file cannot be read from upload

        Example:
            >>> service = StorageService()
            >>> blob_key = service.store_raw_blob(uploaded_file)
            >>> # blob_key is now "blob_550e8400-e29b-41d4-a716-446655440000"
        """
        # Generate unique blob ID
        blob_id = uuid.uuid4()
        blob_key = f"blob_{blob_id}"

        # Construct final and temporary file paths
        file_path = self._storage_dir / f"{blob_id}.bin"
        temp_path = self._storage_dir / f"{blob_id}.tmp"

        try:
            # Stream write with size enforcement
            bytes_written = 0

            with open(temp_path, "wb") as f:
                while True:
                    # Read chunk
                    chunk = file.file.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    # Enforce size limit
                    bytes_written += len(chunk)
                    if bytes_written > self._max_blob_size:
                        temp_path.unlink(missing_ok=True)
                        raise AppError(
                            code=ErrorCode.VALIDATION_ERROR,
                            http_status=422,
                            message=f"File exceeds maximum size of {self._max_blob_size / (1024 * 1024):.0f}MB",
                        )

                    # Write chunk
                    f.write(chunk)

            # Atomic rename: temp → final only on successful completion
            temp_path.replace(file_path)

        except AppError:
            # Clean up temp file on validation error
            temp_path.unlink(missing_ok=True)
            raise
        except Exception:
            # Clean up temp file on any other error
            temp_path.unlink(missing_ok=True)
            raise

        return blob_key

    def open_blob(self, key: str) -> BinaryIO:
        """Open a stored blob for reading.

        Args:
            key: Blob key in format "blob_<uuid>"

        Returns:
            File object opened in binary read mode

        Raises:
            FileNotFoundError: If blob does not exist

        Example:
            >>> service = StorageService()
            >>> with service.open_blob("blob_550e8400-e29b-41d4-a716-446655440000") as f:
            ...     data = f.read()
        """
        # Extract UUID from key (format: "blob_<uuid>")
        blob_id = key.replace("blob_", "")
        file_path = self._storage_dir / f"{blob_id}.bin"

        if not file_path.exists():
            raise FileNotFoundError(f"Blob not found: {key}")

        return open(file_path, "rb")
