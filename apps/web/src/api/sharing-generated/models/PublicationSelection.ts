/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Owner-approved object/field selection; refresh never expands these lists.
 */
export type PublicationSelection = {
    project_id: string;
    experiment_ids?: Array<string>;
    run_refs?: Array<string>;
    parameter_keys?: Array<string>;
    metric_keys?: Array<string>;
    include_descriptions?: boolean;
};

