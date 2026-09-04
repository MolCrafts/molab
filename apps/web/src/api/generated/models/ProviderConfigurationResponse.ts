/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TierModelsResponse } from './TierModelsResponse';
/**
 * One provider's credentials (+ legacy per-provider tier models).
 */
export type ProviderConfigurationResponse = {
    provider: string;
    models?: TierModelsResponse;
    baseUrl?: string;
    apiKeyPreview?: string;
    apiKeySet?: boolean;
};

