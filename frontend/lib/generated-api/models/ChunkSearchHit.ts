/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Single search result in response.
 *
 * Attributes:
 * chunk_id: UUID of matched chunk (typed ID: chunk_<uuid>)
 * document_id: UUID of parent document (typed ID: doc_<uuid>)
 * score: Similarity score (0-1, higher is more similar)
 * text: Chunk text
 * text_start: Byte offset of chunk start
 * text_end: Byte offset of chunk end
 */
export type ChunkSearchHit = {
    /**
     * Chunk ID (typed: chunk_<uuid>)
     */
    chunk_id: string;
    /**
     * Document ID (typed: doc_<uuid>)
     */
    document_id: string;
    /**
     * Similarity score (0-1)
     */
    score: number;
    /**
     * Chunk text content
     */
    text: string;
    /**
     * Byte offset start
     */
    text_start: number;
    /**
     * Byte offset end
     */
    text_end: number;
};

