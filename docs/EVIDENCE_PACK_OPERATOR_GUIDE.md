# Evidence Pack Operator Guide

Evidence packs are the primary proof artifact for the Agent Control Plane pilot.
They connect a governed run to policy decisions, approval state, audit envelope,
replay/signature checks, and claim boundaries.

## Generate

Export evidence for a run:

```bash
uv run imperaos control-plane evidence export \
  --run-id <run-id> \
  --profile enterprise \
  --json
```

The default output path is:

```text
artifacts/control-plane/evidence/<run-id>/manifest.json
```

Use `--output` to write to another directory and `--force` only when replacing a
known local artifact.

## Verify

Verify a manifest:

```bash
uv run imperaos control-plane evidence verify \
  --path artifacts/control-plane/evidence/<run-id>/manifest.json \
  --profile enterprise \
  --json
```

The Operator Panel Evidence page runs the same verification path through the
bridge. The page must show a disabled reason when the current snapshot has no
evidence pack.

## Gate

Run:

```bash
make evidence-pack-gate
```

The gate checks valid evidence, tamper rejection, missing artifact handling, and
the Operator Panel evidence workspace.

## Pack Contents

A pilot-ready evidence pack should include:

- run summary,
- policy decisions,
- approval timeline,
- identity assertion,
- audit envelope,
- replay verification,
- signature verification,
- redaction summary,
- claim guard matrix or linked claim guard result.

## Pass And Block Criteria

`pass` means the pack is structurally valid and verification checks succeeded
for the scoped run. It does not prove external business correctness.

`blocked` or `fail` means the pack cannot support a readiness claim. Treat
signature failure, tamper detection, missing required artifacts, and replay
verification failure as no-ship conditions.

## Claim Boundary

Evidence packs may support the constrained self-hosted Agent Control Plane pilot
claim. They do not unlock live computer-use or public desktop installer claims
unless those separate qualification artifacts exist and the claim guard agrees.
