"""Export isolated sharing contracts without a live cluster or user service."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import TypeAdapter

from molab.server.sharing import create_sharing_app
from molab.sharing.models import (
    AssetInventoryItem,
    AssetShareRequest,
    AssetSharingCapabilities,
    InventoryProject,
    PreviewResponse,
    PublicationSelection,
    PublishRequest,
)
from molab.sharing.settings import GatewaySettings


def main() -> None:
    with TemporaryDirectory() as directory:
        app = create_sharing_app(
            GatewaySettings(
                issuer="schema-export",
                proxy_key="schema-export-only-" + "x" * 32,
                public_origin="http://localhost/",
                state_dir=Path(directory) / "state",
                local_state_confirmed=True,
            )
        )
        schema = app.openapi()
    # Worker-side contracts share these exact domain models, without importing
    # or starting its workspace app or discovering third-party plugins.
    worker_contract = TypeAdapter(
        tuple[
            InventoryProject,
            PreviewResponse,
            PublicationSelection,
            PublishRequest,
            AssetInventoryItem,
            AssetShareRequest,
            AssetSharingCapabilities,
        ]
    )
    schema["components"]["schemas"].update(
        worker_contract.json_schema(ref_template="#/components/schemas/{model}")["$defs"]
    )
    target = Path(__file__).resolve().parents[1] / "sharing.openapi.json"
    target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
