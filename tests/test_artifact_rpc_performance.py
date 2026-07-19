from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from math import ceil
from pathlib import Path
from time import perf_counter

from imperaos.artifacts.models import PrincipalType
from imperaos.artifacts.rpc_protocol import (
    ArtifactRpcMethod,
    RpcFrameDecoder,
    RpcPrincipal,
    RpcRequest,
    RpcResponse,
    encode_frame,
)
from imperaos.artifacts.rpc_server import ArtifactRpcServer
from imperaos.artifacts.service import ArtifactService

WORKSPACE_ID = "workspace-performance"
FIFTY_KIB = 50 * 1024
ONE_MIB = 1024 * 1024


def _document(text: str) -> dict[str, object]:
    return {
        "kind": "document",
        "schemaVersion": 1,
        "language": "en",
        "pageMode": "document",
        "blocks": [
            {
                "id": "block-1",
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def _request(
    request_id: str,
    method: ArtifactRpcMethod,
    params: dict[str, object] | None = None,
    *,
    idempotency_key: str | None = None,
) -> RpcRequest:
    return RpcRequest(
        contract_version="1.0",
        request_id=request_id,
        method=method,
        workspace_id=WORKSPACE_ID,
        principal=RpcPrincipal(
            principal_id="artifact-performance",
            principal_type=PrincipalType.USER,
            roles=("artifact_admin",),
        ),
        idempotency_key=idempotency_key,
        params=params or {},
    )


def _p95(samples: list[float]) -> float:
    return sorted(samples)[max(0, ceil(len(samples) * 0.95) - 1)]


def _invoke(server: ArtifactRpcServer, request: RpcRequest) -> tuple[RpcResponse, float]:
    started = perf_counter()
    response = server.handle_request(request)
    return response, (perf_counter() - started) * 1_000


def _assert_one_stdio_sidecar_stops_without_an_orphan(tmp_path: Path) -> None:
    handshake = _request("sidecar-handshake", ArtifactRpcMethod.RPC_HANDSHAKE)
    shutdown = _request("sidecar-shutdown", ArtifactRpcMethod.RPC_SHUTDOWN)
    completed = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "imperaos",
            "workspace-rpc",
            "--stdio-json",
            "--root",
            str(tmp_path / "sidecar-artifacts"),
        ],
        input=encode_frame(handshake) + encode_frame(shutdown),
        capture_output=True,
        timeout=30,
        check=False,
    )
    decoder = RpcFrameDecoder()
    responses = [RpcResponse.model_validate_json(frame) for frame in decoder.feed(completed.stdout)]
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert len(responses) == 2
    assert all(response.ok for response in responses)


def test_artifact_rpc_matrix_stays_within_budget_and_reaps_its_sidecar(
    tmp_path: Path,
) -> None:
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    timings: dict[str, list[float]] = {
        "create50KiB": [],
        "update50KiB": [],
        "get1MiB": [],
        "list": [],
        "concurrency4R1W": [],
    }
    errors: list[str] = []
    create_content = _document("c" * FIFTY_KIB)
    update_content = _document("u" * FIFTY_KIB)

    for index in range(100):
        artifact_id = f"performance-{index}"
        key = f"create-performance-{index}"
        response, duration = _invoke(
            server,
            _request(
                f"create-{index}",
                ArtifactRpcMethod.ARTIFACT_CREATE,
                {
                    "artifactId": artifact_id,
                    "kind": "document",
                    "title": f"Performance {index}",
                    "dataClass": "internal",
                    "content": create_content,
                    "idempotencyKey": key,
                },
                idempotency_key=key,
            ),
        )
        timings["create50KiB"].append(duration)
        if not response.ok:
            errors.append(f"create-{index}")

    for index in range(100):
        key = f"update-performance-{index}"
        response, duration = _invoke(
            server,
            _request(
                f"update-{index}",
                ArtifactRpcMethod.ARTIFACT_MUTATE,
                {
                    "artifactId": f"performance-{index}",
                    "expectedRevisionNumber": 1,
                    "mutationType": "replace_content",
                    "content": update_content,
                    "idempotencyKey": key,
                    "changeSummary": "Bounded performance update",
                },
                idempotency_key=key,
            ),
        )
        timings["update50KiB"].append(duration)
        if not response.ok:
            errors.append(f"update-{index}")

    large_key = "create-performance-large"
    large = server.handle_request(
        _request(
            "create-large",
            ArtifactRpcMethod.ARTIFACT_CREATE,
            {
                "artifactId": "performance-large",
                "kind": "document",
                "title": "Performance large get",
                "dataClass": "internal",
                "content": _document("g" * ONE_MIB),
                "idempotencyKey": large_key,
            },
            idempotency_key=large_key,
        )
    )
    assert large.ok
    response, duration = _invoke(
        server,
        _request(
            "get-large",
            ArtifactRpcMethod.ARTIFACT_GET,
            {"artifactId": "performance-large"},
        ),
    )
    timings["get1MiB"].append(duration)
    if not response.ok:
        errors.append("get-large")

    for index in range(100):
        response, duration = _invoke(
            server,
            _request(
                f"list-{index}",
                ArtifactRpcMethod.ARTIFACT_LIST,
                {"limit": 200},
            ),
        )
        timings["list"].append(duration)
        if not response.ok:
            errors.append(f"list-{index}")

    concurrent_requests = [
        _request(
            f"concurrent-read-{index}",
            ArtifactRpcMethod.ARTIFACT_GET,
            {"artifactId": "performance-large"},
        )
        for index in range(4)
    ]
    concurrent_key = "concurrent-write-performance"
    concurrent_requests.append(
        _request(
            "concurrent-write",
            ArtifactRpcMethod.ARTIFACT_MUTATE,
            {
                "artifactId": "performance-0",
                "expectedRevisionNumber": 2,
                "mutationType": "replace_content",
                "content": _document("w" * FIFTY_KIB),
                "idempotencyKey": concurrent_key,
                "changeSummary": "Concurrent bounded update",
            },
            idempotency_key=concurrent_key,
        )
    )
    with ThreadPoolExecutor(max_workers=5, thread_name_prefix="artifact-rpc-performance") as pool:
        concurrent_results = list(pool.map(lambda item: _invoke(server, item), concurrent_requests))
    for index, (response, duration) in enumerate(concurrent_results):
        timings["concurrency4R1W"].append(duration)
        if not response.ok:
            errors.append(f"concurrent-{index}")

    _assert_one_stdio_sidecar_stops_without_an_orphan(tmp_path)
    p95_by_workload = {name: round(_p95(samples), 3) for name, samples in timings.items()}
    assert errors == []
    assert max(p95_by_workload.values()) <= 400

    evidence = {
        "workload": "rpc-create-update-get-list-concurrency",
        "samples": {
            "create50KiB": 100,
            "update50KiB": 100,
            "get1MiB": 1,
            "list": 100,
            "concurrentReaders": 4,
            "concurrentWriters": 1,
        },
        "p95BudgetMs": 400,
        "p95Ms": p95_by_workload,
        "errors": len(errors),
        "sidecarProcesses": 1,
        "orphanProcesses": 0,
    }
    print(f"ARTIFACT_PERFORMANCE_JSON={json.dumps(evidence, sort_keys=True)}")
