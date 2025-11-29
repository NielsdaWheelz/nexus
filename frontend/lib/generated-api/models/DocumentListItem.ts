/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * API response schema for a single document in list endpoint.
 *
 * This is the document representation returned by GET /documents.
 * All IDs are typed (doc_<uuid>), timestamps are ISO8601 UTC.
 *
 * Attributes:
 * id: Typed document ID (doc_<uuid>)
 * title: Document title
 * source_kind: Type of source (pdf, epub, html)
 * processing_status: Current processing state (pending, processing, ready, failed)
 * created_at: UTC timestamp when document was uploaded
 * updated_at: UTC timestamp of last update
 */
export type DocumentListItem = {
    /**
     * Typed document ID (doc_<uuid>)
     */
    id: string;
    /**
     * Document title (may be None)
     */
    title: (string | null);
    /**
     * Type of source document
     */
    source_kind: DocumentListItem.source_kind;
    /**
     * Current processing state
     */
    processing_status: DocumentListItem.processing_status;
    /**
     * UTC timestamp of upload
     */
    created_at: string;
    /**
     * UTC timestamp of last update
     */
    updated_at: string;
};
export namespace DocumentListItem {
    /**
     * Type of source document
     */
    export enum source_kind {
        PDF = 'pdf',
        EPUB = 'epub',
        HTML = 'html',
    }
    /**
     * Current processing state
     */
    export enum processing_status {
        PENDING = 'pending',
        PROCESSING = 'processing',
        READY = 'ready',
        FAILED = 'failed',
    }
}

