"""Initial schema creation for Phase 1.

This migration creates all Phase 1 tables with proper constraints and indexes.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial Phase 1 schema."""

    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('external_user_id', sa.Text(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_user_id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('idx_users_external_user_id', 'users', ['external_user_id'])

    # documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('author', sa.String(255), nullable=True),
        sa.Column('published_date', sa.String(10), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('original_blob_key', sa.Text(), nullable=False),
        sa.Column('original_mime_type', sa.String(100), nullable=False),
        sa.Column('original_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('canonical_text', sa.Text(), nullable=False),
        sa.Column('canonical_hash', sa.String(64), nullable=False),
        sa.Column('canonical_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('text_byte_length', sa.Integer(), nullable=False),
        sa.Column('extractor_version', sa.String(50), nullable=False),
        sa.Column('structure', postgresql.JSON(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('language', sa.String(10), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_code', sa.String(100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retries_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_attempted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('embedding_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('embedding_model', sa.String(100), nullable=True),
        sa.Column('chunk_version', sa.String(50), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'processing', 'ready', 'failed')", name='ck_documents_status'),
        sa.CheckConstraint("embedding_status IN ('pending', 'ready', 'failed')", name='ck_documents_embedding_status'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_documents_user', 'documents', ['user_id'])
    op.create_index('idx_documents_status', 'documents', ['status'], postgresql_where=sa.text("status != 'ready' AND deleted_at IS NULL"))
    op.create_index('idx_documents_embedding_status', 'documents', ['embedding_status'], postgresql_where=sa.text("embedding_status != 'ready' AND deleted_at IS NULL"))
    op.create_index('idx_documents_content_hash', 'documents', ['content_hash'])

    # highlights table
    op.create_table(
        'highlights',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('media_type', sa.String(20), nullable=False),
        sa.Column('media_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('anchor_type', sa.String(20), nullable=False),
        sa.Column('text_start', sa.BigInteger(), nullable=False),
        sa.Column('text_end', sa.BigInteger(), nullable=False),
        sa.Column('quote', sa.Text(), nullable=False),
        sa.Column('prefix', sa.Text(), nullable=False),
        sa.Column('suffix', sa.Text(), nullable=False),
        sa.Column('canonical_version', sa.Integer(), nullable=True),
        sa.Column('transcript_hash', sa.String(64), nullable=True),
        sa.Column('pdf_page_number', sa.Integer(), nullable=True),
        sa.Column('pdf_char_offset', sa.Integer(), nullable=True),
        sa.Column('pdf_extraction_confidence', sa.Float(), nullable=True),
        sa.Column('pdf_file_hash', sa.String(64), nullable=True),
        sa.Column('time_start', sa.Float(), nullable=True),
        sa.Column('time_end', sa.Float(), nullable=True),
        sa.Column('color', sa.String(20), nullable=False, server_default='yellow'),
        sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_detached', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('detached_reason', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('text_end > text_start', name='ck_highlights_text_range'),
        sa.CheckConstraint("media_type IN ('document', 'episode', 'video')", name='ck_highlights_media_type'),
        sa.CheckConstraint("anchor_type IN ('text', 'pdf', 'transcript')", name='ck_highlights_anchor_type'),
        sa.CheckConstraint("color IN ('yellow', 'blue', 'green', 'pink', 'purple')", name='ck_highlights_color'),
        sa.CheckConstraint(
            "(media_type = 'document' AND canonical_version IS NOT NULL AND transcript_hash IS NULL) OR "
            "(media_type IN ('episode', 'video') AND transcript_hash IS NOT NULL AND canonical_version IS NULL)",
            name='ck_highlights_version_anchor'
        ),
        sa.CheckConstraint(
            "(anchor_type = 'text' AND pdf_page_number IS NULL AND pdf_char_offset IS NULL AND "
            "pdf_extraction_confidence IS NULL AND pdf_file_hash IS NULL AND time_start IS NULL AND time_end IS NULL) OR "
            "(anchor_type = 'pdf' AND pdf_page_number IS NOT NULL AND pdf_char_offset IS NOT NULL AND "
            "pdf_file_hash IS NOT NULL AND time_start IS NULL AND time_end IS NULL) OR "
            "(anchor_type = 'transcript' AND time_start IS NOT NULL AND time_end IS NOT NULL AND "
            "pdf_page_number IS NULL AND pdf_char_offset IS NULL AND pdf_extraction_confidence IS NULL AND pdf_file_hash IS NULL)",
            name='ck_highlights_anchor_type_validity'
        ),
        sa.CheckConstraint(
            "(media_type = 'document' AND anchor_type IN ('text', 'pdf')) OR "
            "(media_type IN ('episode', 'video') AND anchor_type = 'transcript')",
            name='ck_highlights_media_anchor_compatibility'
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_highlights_user', 'highlights', ['user_id'], postgresql_where=sa.text("NOT is_hidden AND deleted_at IS NULL"))
    op.create_index('idx_highlights_media', 'highlights', ['media_type', 'media_id'], postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index('idx_highlights_anchor_type', 'highlights', ['anchor_type'])
    op.create_index('idx_highlights_pdf', 'highlights', ['media_id', 'pdf_page_number'], postgresql_where=sa.text("anchor_type = 'pdf' AND deleted_at IS NULL"))
    op.create_index('idx_highlights_transcript', 'highlights', ['media_id', 'time_start'], postgresql_where=sa.text("anchor_type = 'transcript' AND deleted_at IS NULL"))

    # annotations table
    op.create_table(
        'annotations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('highlight_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['highlight_id'], ['highlights.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_annotations_highlight', 'annotations', ['highlight_id'], postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index('idx_annotations_user', 'annotations', ['user_id'], postgresql_where=sa.text("deleted_at IS NULL"))

    # conversations table
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('summary_state', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('summary_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_conversations_user', 'conversations', ['user_id'], postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index('idx_conversations_public', 'conversations', ['is_public'], postgresql_where=sa.text("is_public = TRUE AND deleted_at IS NULL"))

    # messages table
    op.create_table(
        'messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('effective_model_id', sa.String(100), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name='ck_messages_role'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_messages_conversation', 'messages', ['conversation_id', 'created_at'], postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_index('idx_messages_user', 'messages', ['user_id'], postgresql_where=sa.text("deleted_at IS NULL"))

    # libraries table
    op.create_table(
        'libraries',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_libraries_user', 'libraries', ['user_id'])
    op.create_index('idx_libraries_public', 'libraries', ['is_public'], postgresql_where=sa.text("is_public = TRUE"))

    # library_memberships table
    op.create_table(
        'library_memberships',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('library_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(20), nullable=False, server_default='viewer'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'editor', 'viewer')", name='ck_library_memberships_role'),
        sa.ForeignKeyConstraint(['library_id'], ['libraries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('library_id', 'user_id', name='uq_library_memberships_library_user'),
    )
    op.create_index('idx_library_memberships_user', 'library_memberships', ['user_id'])
    op.create_index('idx_library_memberships_library', 'library_memberships', ['library_id'])

    # library_media table
    op.create_table(
        'library_media',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('library_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('media_type', sa.String(20), nullable=False),
        sa.Column('media_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('added_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("media_type IN ('document', 'episode', 'video')", name='ck_library_media_type'),
        sa.ForeignKeyConstraint(['library_id'], ['libraries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['added_by_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('library_id', 'media_type', 'media_id', name='uq_library_media_library_media'),
    )
    op.create_index('idx_library_media_library', 'library_media', ['library_id'])
    op.create_index('idx_library_media_media', 'library_media', ['media_type', 'media_id'])

    # object_library_visibility table
    op.create_table(
        'object_library_visibility',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('object_type', sa.String(20), nullable=False),
        sa.Column('object_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('library_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('shared_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("object_type IN ('highlight', 'annotation', 'conversation', 'message')", name='ck_object_visibility_type'),
        sa.ForeignKeyConstraint(['library_id'], ['libraries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shared_by_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('object_type', 'object_id', 'library_id', name='uq_object_visibility_object_library'),
    )
    op.create_index('idx_object_visibility_library', 'object_library_visibility', ['library_id'])
    op.create_index('idx_object_visibility_object', 'object_library_visibility', ['object_type', 'object_id'])

    # links table
    op.create_table(
        'links',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('source_type', sa.String(20), nullable=False),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_type', sa.String(20), nullable=False),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('NOT (source_type = target_type AND source_id = target_id)', name='ck_links_no_self_links'),
        sa.CheckConstraint("source_type IN ('document', 'episode', 'video', 'highlight', 'annotation', 'message', 'conversation')", name='ck_links_valid_source_type'),
        sa.CheckConstraint("target_type IN ('document', 'episode', 'video', 'highlight', 'annotation', 'message', 'conversation')", name='ck_links_valid_target_type'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_type', 'source_id', 'target_type', 'target_id', name='uq_links_canonical'),
    )
    op.create_index('idx_links_source', 'links', ['source_type', 'source_id'])
    op.create_index('idx_links_target', 'links', ['target_type', 'target_id'])
    op.create_index('idx_links_creator', 'links', ['created_by_user_id'])

    # content_chunks table
    op.create_table(
        'content_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('media_type', sa.String(20), nullable=False),
        sa.Column('media_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_version', sa.String(50), nullable=False),
        sa.Column('embedding_model', sa.String(100), nullable=False),
        sa.Column('text_start', sa.BigInteger(), nullable=False),
        sa.Column('text_end', sa.BigInteger(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("media_type IN ('document', 'episode', 'video')", name='ck_content_chunks_media_type'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_content_chunks_media', 'content_chunks', ['media_type', 'media_id'])

    # thought_chunks table
    op.create_table(
        'thought_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('object_type', sa.String(30), nullable=False),
        sa.Column('object_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_version', sa.String(50), nullable=False),
        sa.Column('embedding_model', sa.String(100), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("object_type IN ('annotation', 'message', 'conversation_summary')", name='ck_thought_chunks_object_type'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_thought_chunks_user', 'thought_chunks', ['user_id'])
    op.create_index('idx_thought_chunks_object', 'thought_chunks', ['object_type', 'object_id'])

    # metadata_chunks table
    op.create_table(
        'metadata_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('entity_type', sa.String(20), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chunk_version', sa.String(50), nullable=False),
        sa.Column('embedding_model', sa.String(100), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("entity_type IN ('document', 'episode', 'video', 'podcast')", name='ck_metadata_chunks_entity_type'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_metadata_chunks_entity', 'metadata_chunks', ['entity_type', 'entity_id'])


def downgrade() -> None:
    """Drop all Phase 1 tables."""
    op.drop_index('idx_metadata_chunks_entity', 'metadata_chunks')
    op.drop_table('metadata_chunks')

    op.drop_index('idx_thought_chunks_object', 'thought_chunks')
    op.drop_index('idx_thought_chunks_user', 'thought_chunks')
    op.drop_table('thought_chunks')

    op.drop_index('idx_content_chunks_media', 'content_chunks')
    op.drop_table('content_chunks')

    op.drop_index('idx_links_creator', 'links')
    op.drop_index('idx_links_target', 'links')
    op.drop_index('idx_links_source', 'links')
    op.drop_table('links')

    op.drop_index('idx_object_visibility_object', 'object_library_visibility')
    op.drop_index('idx_object_visibility_library', 'object_library_visibility')
    op.drop_table('object_library_visibility')

    op.drop_index('idx_library_media_media', 'library_media')
    op.drop_index('idx_library_media_library', 'library_media')
    op.drop_table('library_media')

    op.drop_index('idx_library_memberships_library', 'library_memberships')
    op.drop_index('idx_library_memberships_user', 'library_memberships')
    op.drop_table('library_memberships')

    op.drop_index('idx_libraries_public', 'libraries')
    op.drop_index('idx_libraries_user', 'libraries')
    op.drop_table('libraries')

    op.drop_index('idx_messages_user', 'messages')
    op.drop_index('idx_messages_conversation', 'messages')
    op.drop_table('messages')

    op.drop_index('idx_conversations_public', 'conversations')
    op.drop_index('idx_conversations_user', 'conversations')
    op.drop_table('conversations')

    op.drop_index('idx_annotations_user', 'annotations')
    op.drop_index('idx_annotations_highlight', 'annotations')
    op.drop_table('annotations')

    op.drop_index('idx_highlights_transcript', 'highlights')
    op.drop_index('idx_highlights_pdf', 'highlights')
    op.drop_index('idx_highlights_anchor_type', 'highlights')
    op.drop_index('idx_highlights_media', 'highlights')
    op.drop_index('idx_highlights_user', 'highlights')
    op.drop_table('highlights')

    op.drop_index('idx_documents_content_hash', 'documents')
    op.drop_index('idx_documents_embedding_status', 'documents')
    op.drop_index('idx_documents_status', 'documents')
    op.drop_index('idx_documents_user', 'documents')
    op.drop_table('documents')

    op.drop_index('idx_users_external_user_id', 'users')
    op.drop_table('users')

    # Drop extensions
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
