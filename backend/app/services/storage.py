"""Storage service for managing document blobs.

Phase 1 Stub Implementation:
- Stores uploaded files to local /tmp directory
- Returns blob_key for database persistence
- Does NOT implement cloud storage, chunking, async IO, or production features

This is a placeholder for Phase 1. Phase 2+ will add:
- S3 integration
- Content-addressable storage
- Multipart uploads
- Streaming reads

Spec reference:
- PR 4.1 specification (StorageService stub)
"""

import uuid
from pathlib import Path

from fastapi import UploadFile


class StorageService:
    """Phase 1 storage stub.

    Stores uploaded files to /tmp/nexus_blobs/<uuid>.bin and returns a blob_key
    that can be persisted in the database.

    Note: This is a Phase 1 placeholder. Production deployments will use S3 or
    equivalent cloud storage. Files are NOT persisted across restarts.
    """

    def __init__(self) -> None:
        """Initialize storage service (no configuration needed for Phase 1)."""
        self._storage_dir = Path("/tmp/nexus_blobs")
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def store_raw_blob(self, file: UploadFile) -> str:
        """Store uploaded file and return blob_key.

        Phase 1 implementation:
        - Reads entire file into memory (OK for Phase 1, <50MB files)
        - Stores to /tmp/nexus_blobs/<uuid>.bin
        - Returns blob_key = "blob_<uuid>"

        Args:
            file: UploadFile from FastAPI

        Returns:
            blob_key: Opaque string for database persistence (format: "blob_<uuid>")

        Raises:
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

        # Construct file path
        file_path = self._storage_dir / f"{blob_id}.bin"

        # Read file contents and write to storage
        contents = file.file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        return blob_key
