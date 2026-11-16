/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * One byte window of one execution log, for incremental follow.
 *
 * Returned by ``…/logs/{stream}?offset=…``. ``text`` decodes the bytes
 * ``[offset, next_offset)``; a multi-byte character cut by the window is
 * left for the next read, so ``next_offset`` is always a character
 * boundary. A poller passes ``next_offset`` back as ``offset``. ``size`` is
 * the file's size at read time (``0`` when the file does not exist yet);
 * ``eof`` is true when ``next_offset`` reached it.
 */
export type RunLogChunkResponse = {
    stream: RunLogChunkResponse.stream;
    text: string;
    offset: number;
    nextOffset: number;
    size: number;
    eof: boolean;
};
export namespace RunLogChunkResponse {
    export enum stream {
        STDOUT = 'stdout',
        STDERR = 'stderr',
        RUN = 'run',
    }
}

