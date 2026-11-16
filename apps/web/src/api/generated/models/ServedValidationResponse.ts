/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ValidationRow } from './ValidationRow';
/**
 * ``molab validate`` for the served directory and what is below it.
 */
export type ServedValidationResponse = {
    root: string;
    ok: boolean;
    errorCount: number;
    warningCount: number;
    violations: Array<ValidationRow>;
};

