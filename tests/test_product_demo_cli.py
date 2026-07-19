from __future__ import annotations

import json

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_product_demo_memory_smoke_denies_cross_workspace() -> None:
    result = runner.invoke(
        app,
        [
            "product",
            "demo",
            "memory-smoke",
            "--profile",
            "enterprise",
            "--workspace-id",
            "workspace-a",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "product.demo.memory-smoke/v1"
    assert payload["status"] == "pass"
    assert payload["checks"]["crossWorkspaceReadDenied"] is True
    assert payload["checks"]["rawContentExposed"] is False
