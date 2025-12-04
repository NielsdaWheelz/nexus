/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request schema for chunk similarity search.
 *
 * Attributes:
 * query: Search query text (required, 1-2000 chars)
 * limit: Max results to return (optional, 1-100, default 20)
 * document_ids: Optional list of document IDs to restrict search (typed IDs: doc_<uuid>)
 */
export type ChunkSearchRequest = {
    /**
     * Search query (1-2000 characters)
     */
    query: string;
    /**
     * Max results (1-100)
     */
    limit?: number;
    /**
     * Optional list of document IDs to restrict search (typed IDs: doc_<uuid>)
     */
    document_ids?: (Array<string> | null);
};

