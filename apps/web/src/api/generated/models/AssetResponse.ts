/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Serialized typed ``Asset``.
 *
 * ``kind`` is the discriminator (``data`` / ``artifact`` / ``log`` / …).
 * ``extra`` carries subclass-specific fields so the frontend can render
 * per-kind details without a separate schema per kind.
 * ``content_hash`` is the sha256 (``"sha256:<hex>"``) of the payload
 * when the asset is content-addressable; ``None`` for streaming kinds.
 */
export type AssetResponse = {
    contentHash?: (string | null);
    createdAt: string;
    extra?: Record<string, any>;
    hasPreviewSidecar?: boolean;
    id: string;
    kind: string;
    name: string;
    path: string;
    producer?: (Record<string, any> | null);
    scopeIds: Array<string>;
    scopeKind: string;
    tags?: Record<string, string>;
    updatedAt: string;
};

