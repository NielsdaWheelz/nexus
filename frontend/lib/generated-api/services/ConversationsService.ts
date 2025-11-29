/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConversationDetail } from '../models/ConversationDetail';
import type { ConversationListResponse } from '../models/ConversationListResponse';
import type { CreateConversationRequest } from '../models/CreateConversationRequest';
import type { CreateMessageRequest } from '../models/CreateMessageRequest';
import type { MessageListItem } from '../models/MessageListItem';
import type { MessageListResponse } from '../models/MessageListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ConversationsService {
    /**
     * Create conversation
     * Create a new conversation with optional document reference.
     * @param requestBody
     * @param authorization
     * @returns ConversationDetail Successful Response
     * @throws ApiError
     */
    public static createConversationConversationsPost(
        requestBody: CreateConversationRequest,
        authorization?: (string | null),
    ): CancelablePromise<ConversationDetail> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/conversations',
            headers: {
                'authorization': authorization,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List conversations
     * List user's conversations with cursor-based pagination.
     * @param limit
     * @param cursor
     * @param authorization
     * @returns ConversationListResponse Successful Response
     * @throws ApiError
     */
    public static listConversationsConversationsGet(
        limit: number = 20,
        cursor?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<ConversationListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/conversations',
            headers: {
                'authorization': authorization,
            },
            query: {
                'limit': limit,
                'cursor': cursor,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get conversation
     * Retrieve a single conversation by ID.
     * @param conversationId
     * @param authorization
     * @returns ConversationDetail Successful Response
     * @throws ApiError
     */
    public static getConversationConversationsConversationIdGet(
        conversationId: string,
        authorization?: (string | null),
    ): CancelablePromise<ConversationDetail> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/conversations/{conversation_id}',
            path: {
                'conversation_id': conversationId,
            },
            headers: {
                'authorization': authorization,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List messages
     * List messages in a conversation with cursor-based pagination.
     * @param conversationId
     * @param limit
     * @param cursor
     * @param authorization
     * @returns MessageListResponse Successful Response
     * @throws ApiError
     */
    public static listMessagesConversationsConversationIdMessagesGet(
        conversationId: string,
        limit: number = 50,
        cursor?: (string | null),
        authorization?: (string | null),
    ): CancelablePromise<MessageListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/conversations/{conversation_id}/messages',
            path: {
                'conversation_id': conversationId,
            },
            headers: {
                'authorization': authorization,
            },
            query: {
                'limit': limit,
                'cursor': cursor,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Append user message
     * Append a user message to a conversation.
     * @param conversationId
     * @param requestBody
     * @param authorization
     * @returns MessageListItem Successful Response
     * @throws ApiError
     */
    public static createMessageConversationsConversationIdMessagesPost(
        conversationId: string,
        requestBody: CreateMessageRequest,
        authorization?: (string | null),
    ): CancelablePromise<MessageListItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/conversations/{conversation_id}/messages',
            path: {
                'conversation_id': conversationId,
            },
            headers: {
                'authorization': authorization,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
