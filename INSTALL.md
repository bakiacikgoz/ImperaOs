# Install

After installation, validate the Agent Control Plane boundary with
`uv run imperaos control-plane doctor --profile enterprise --json` before
claiming governed agent production-readiness.

## Supported Baseline

- Linux runtime host for primary deployment
- macOS for operator tooling and local verification tasks
- Windows x64 for core CLI, operator panel, bundled runtime, and installer smoke
- Python 3.11
- `uv` package manager

## Online Install

```bash
make install
uv run imperaos --version
uv run imperaos doctor --profile balanced
```

## Windows Online Install

```powershell
winget install --id=astral-sh.uv -e
uv sync --python 3.11 --extra dev
uv run python -m imperaos --version
uv run python -m imperaos doctor --profile balanced --json
uv run python -m imperaos operator capabilities --json
```

Alternative uv installer:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Windows support currently covers core CLI and operator-panel packaging. Windows
live computer-use automation remains disabled unless a Windows qualification
report explicitly enables it.

For a full Windows developer setup, use the bootstrap script:

```powershell
pwsh scripts/bootstrap_windows.ps1
```

The script uses frozen Python and UI dependency installs. It checks for `uv`,
Node/Corepack/pnpm, Rust, and reports WebView2 prerequisite status without
installing system components automatically.

## Enterprise Fixture Preparation

For local enterprise validation, prepare signing keys and a verified identity assertion:

```bash
uv run python scripts/prepare_enterprise_fixture.py --root .
```

## Offline Install

Expected offline bundle contents:

- pinned wheelhouse or dependency cache
- application source or built artifact
- config templates
- policy bundle manifest
- key bootstrap instructions

## Enterprise Validation After Install

```bash
uv run imperaos security baseline --profile enterprise --json
uv run imperaos auth whoami --profile enterprise --json
uv run imperaos ga readiness --profile enterprise --report artifacts/ga_readiness_report.json --json
```
# Product-Complete First Run

After installing Python, `uv`, Node/Corepack/pnpm, and the Rust toolchain, run:

```bash
uv sync --python 3.11 --extra dev
corepack pnpm --dir apps/operator-panel install --frozen-lockfile
uv run imperaos setup first-run --profile enterprise --mode local-enterprise --json
```

The diagnostic command is non-destructive and reports setup-required reason
codes instead of pretending the product is ready.
