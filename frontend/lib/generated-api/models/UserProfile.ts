/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Current user profile response.
 */
export type UserProfile = {
    /**
     * Typed user ID (usr_<uuid>)
     */
    id: string;
    /**
     * User email address
     */
    email: string;
    /**
     * Display name (derived from email)
     */
    display_name: string;
    /**
     * UTC timestamp of account creation
     */
    created_at: string;
    /**
     * UTC timestamp of last update
     */
    updated_at: string;
};

