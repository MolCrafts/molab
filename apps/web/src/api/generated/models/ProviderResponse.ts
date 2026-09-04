/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProviderConfigurationResponse } from './ProviderConfigurationResponse';
import type { TierModelsResponse } from './TierModelsResponse';
/**
 * The Settings page's provider view — never carries a key value.
 */
export type ProviderResponse = {
    provider: string;
    model: string;
    baseUrl: string;
    apiKeyPreview: string;
    apiKeySet: boolean;
    instructions: string;
    supportedProviders?: Array<string>;
    models?: TierModelsResponse;
    configurations?: Array<ProviderConfigurationResponse>;
};

