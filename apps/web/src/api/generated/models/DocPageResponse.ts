/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * ``GET /knowledge/doc/page``: one document as a self-contained HTML page.
 */
export type DocPageResponse = {
    title: string;
    /**
     * The whole page; every asset it shows is inlined.
     */
    html: string;
};

