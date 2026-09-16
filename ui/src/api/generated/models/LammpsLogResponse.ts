/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LammpsThermoStage } from './LammpsThermoStage';
/**
 * Parsed LAMMPS log thermo stages, produced by ``molpy.io.LAMMPSLog``.
 *
 * A long MD run's log can be gigabytes.  Above the parse ceiling the server
 * parses only the *tail* — the latest stages, which is what a progress view
 * wants — and sets ``truncated``.  ``bytesParsed`` is how much was actually
 * read, so a caller can tell a whole-file parse from a windowed one (and
 * ``version``, read from line 1, is absent in the windowed case).
 */
export type LammpsLogResponse = {
    bytesParsed?: number;
    nStages?: number;
    path: string;
    stages?: Array<LammpsThermoStage>;
    truncated?: boolean;
    version?: (string | null);
};

