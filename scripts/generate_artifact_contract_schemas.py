from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.artifacts.commands import (  # noqa: E402
    ApplyArtifactProposalCommand,
    ArchiveArtifactCommand,
    ArtifactHistoryQuery,
    BeginArtifactExportCommand,
    CancelArtifactExportCommand,
    CommitArtifactExportCommand,
    CreateArtifactCommand,
    DuplicateArtifactCommand,
    GetArtifactAssetQuery,
    GetArtifactQuery,
    ImportArtifactAssetCommand,
    ImportEvidenceArtifactCommand,
    ListArtifactsQuery,
    MutateArtifactCommand,
    PatchArtifactSlideCommand,
    PatchSpreadsheetCellsCommand,
    PreflightArtifactExportCommand,
    ProposeArtifactMutationCommand,
    RestoreArtifactCommand,
    SubmitArtifactFormCommand,
)
from imperaos.artifacts.content import (  # noqa: E402
    CanvasContentV1,
    CanvasContentV2,
    CodeContentV1,
    CodeContentV2,
    DocumentContentV1,
    FlowContentV1,
    FlowContentV2,
    FormContentV1,
    SafeJsonPatch,
    SlidesContentV1,
    SlidesContentV2,
    SpreadsheetContentV1,
    SpreadsheetContentV2,
)
from imperaos.artifacts.evidence import ArtifactEvidenceEvent  # noqa: E402
from imperaos.artifacts.licenses import (  # noqa: E402
    ArtifactLicenseCapability,
    ArtifactLicenseDoctorResult,
)
from imperaos.artifacts.models import (  # noqa: E402
    ArtifactAssetDescriptor,
    ArtifactDescriptor,
    ArtifactRevisionDescriptor,
    OperationContext,
)
from imperaos.artifacts.results import (  # noqa: E402
    ArtifactAssetImportResult,
    ArtifactAssetReadResult,
    ArtifactExportBeginResult,
    ArtifactExportResult,
    ArtifactFormSubmissionResult,
)
from imperaos.artifacts.rpc_protocol import (  # noqa: E402
    RpcError,
    RpcHandshake,
    RpcPrincipal,
    RpcRequest,
    RpcResponse,
)

SCHEMAS = {
    "document.v1": DocumentContentV1,
    "form.v1": FormContentV1,
    "code.v1": CodeContentV1,
    "code.v2": CodeContentV2,
    "flow.v1": FlowContentV1,
    "flow.v2": FlowContentV2,
    "spreadsheet.v1": SpreadsheetContentV1,
    "spreadsheet.v2": SpreadsheetContentV2,
    "canvas.v1": CanvasContentV1,
    "canvas.v2": CanvasContentV2,
    "slides.v1": SlidesContentV1,
    "slides.v2": SlidesContentV2,
    "artifact-descriptor.v1": ArtifactDescriptor,
    "artifact-asset.v1": ArtifactAssetDescriptor,
    "artifact-revision.v1": ArtifactRevisionDescriptor,
    "operation-context.v1": OperationContext,
    "safe-json-patch.v1": SafeJsonPatch,
    "artifact-create-command.v1": CreateArtifactCommand,
    "artifact-get-query.v1": GetArtifactQuery,
    "artifact-list-query.v1": ListArtifactsQuery,
    "artifact-mutation-command.v1": MutateArtifactCommand,
    "artifact-spreadsheet-cell-patch-command.v1": PatchSpreadsheetCellsCommand,
    "artifact-slide-patch-command.v1": PatchArtifactSlideCommand,
    "artifact-mutation-proposal-command.v1": ProposeArtifactMutationCommand,
    "artifact-apply-proposal-command.v1": ApplyArtifactProposalCommand,
    "artifact-history-query.v1": ArtifactHistoryQuery,
    "artifact-restore-command.v1": RestoreArtifactCommand,
    "artifact-archive-command.v1": ArchiveArtifactCommand,
    "artifact-duplicate-command.v1": DuplicateArtifactCommand,
    "artifact-asset-import-command.v1": ImportArtifactAssetCommand,
    "artifact-asset-get-query.v1": GetArtifactAssetQuery,
    "artifact-asset-import-result.v1": ArtifactAssetImportResult,
    "artifact-asset-read-result.v1": ArtifactAssetReadResult,
    "artifact-import-evidence-command.v1": ImportEvidenceArtifactCommand,
    "artifact-form-submit-command.v1": SubmitArtifactFormCommand,
    "artifact-form-submit-result.v1": ArtifactFormSubmissionResult,
    "artifact-export-begin-command.v1": BeginArtifactExportCommand,
    "artifact-export-commit-command.v1": CommitArtifactExportCommand,
    "artifact-export-preflight-command.v1": PreflightArtifactExportCommand,
    "artifact-export-cancel-command.v1": CancelArtifactExportCommand,
    "artifact-export-begin-result.v1": ArtifactExportBeginResult,
    "artifact-export-result.v1": ArtifactExportResult,
    "artifact-license-capability.v1": ArtifactLicenseCapability,
    "artifact-license-doctor-result.v1": ArtifactLicenseDoctorResult,
    "artifact-evidence-event.v1": ArtifactEvidenceEvent,
    "artifact-rpc-principal.v1": RpcPrincipal,
    "artifact-rpc-request.v1": RpcRequest,
    "artifact-rpc-response.v1": RpcResponse,
    "artifact-rpc-error.v1": RpcError,
    "artifact-rpc-handshake.v1": RpcHandshake,
}
CONTENT_SCHEMA_NAMES = {
    "document.v1",
    "form.v1",
    "code.v1",
    "code.v2",
    "flow.v1",
    "flow.v2",
    "spreadsheet.v1",
    "spreadsheet.v2",
    "canvas.v1",
    "canvas.v2",
    "slides.v1",
    "slides.v2",
}


def schema_for(name: str, model: type[Any]) -> dict[str, Any]:
    schema = model.model_json_schema(by_alias=True)
    schema["$id"] = f"https://schemas.imperaos.local/artifacts/{name}.schema.json"
    schema["x-imperaos-contract"] = name
    if name == "form.v1":
        schema["x-imperaos-security"] = {
            "validator": "CSP-safe ValidatorType; global unsafe-eval is forbidden",
            "refs": "local definitions only; remote $ref is forbidden",
            "authority": "backend revalidation is mandatory",
        }
    if name == "code.v2":
        unicode_format_characters = (
            "\u00ad\u0600-\u0605\u061c\u06dd\u070f\u0890-\u0891\u08e2\u180e"
            "\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff\ufff9-\ufffb"
            f"{chr(0x110BD)}{chr(0x110CD)}{chr(0x13430)}-{chr(0x1343F)}"
            f"{chr(0x1BCA0)}-{chr(0x1BCA3)}{chr(0x1D173)}-{chr(0x1D17A)}"
            f"{chr(0xE0001)}{chr(0xE0020)}-{chr(0xE007F)}"
        )
        schema["properties"]["filename"]["pattern"] = (
            r"^(?![ .])(?!.*[ .]$)"
            r"(?!(?:[Cc][Oo][Nn]|[Pp][Rr][Nn]|[Aa][Uu][Xx]|[Nn][Uu][Ll]|"
            r"[Cc][Oo][Mm][1-9]|[Ll][Pp][Tt][1-9])(?:\.|$))"
            r"[^<>:\"/\\|?*\u0000-\u001f\u007f-\u009f"
            + unicode_format_characters
            + r"]+$"
        )
        schema["allOf"] = [
            {
                "if": {
                    "properties": {"lineEnding": {"const": "crlf"}},
                    "required": ["lineEnding"],
                },
                "then": {
                    "properties": {
                        "text": {
                            "pattern": r"^(?![\s\S]*(?:\r(?!\n)|[^\r]\n|^\n))[\s\S]*$"
                        }
                    }
                },
                "else": {"properties": {"text": {"pattern": r"^[^\r]*$"}}},
            }
        ]
    if name == "safe-json-patch.v1":
        schema["x-imperaos-security"] = {
            "operations": "add/remove/replace/test only",
            "paths": "prototype pollution segments are forbidden",
        }
    return schema


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> None:
    root = REPO_ROOT / "contracts" / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict[str, str]] = []
    for name, model in SCHEMAS.items():
        filename = f"{name}.schema.json"
        payload = _canonical_json(schema_for(name, model))
        payload_bytes = payload.encode("utf-8")
        (root / filename).write_bytes(payload_bytes)
        manifest_entries.append(
            {
                "name": name,
                "file": filename,
                "sha256": hashlib.sha256(payload_bytes).hexdigest(),
                "category": "content" if name in CONTENT_SCHEMA_NAMES else "contract",
            }
        )
    manifest = {
        "schemaVersion": "artifact-workspace.contract-manifest/v1",
        "generatedFrom": "imperaos.artifacts",
        "schemas": manifest_entries,
    }
    (root / "manifest.json").write_bytes(_canonical_json(manifest).encode("utf-8"))


if __name__ == "__main__":
    main()
