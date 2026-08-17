# Support Bundle

Support bundles are part of the Agent Control Plane evidence story. They must
remain redacted and may be referenced by control-plane evidence manifests, but
they do not by themselves authorize public desktop or live computer-use claims.

## Goal

The support bundle provides a redacted, signed export that gives operators and support engineers enough evidence to triage runtime issues without handing over raw secrets or unrestricted logs.

## Command

```bash
uv run imperaos support bundle export --profile enterprise --json
```

## Included Content

- version and build information available in the current workspace
- redacted resolved config
- metrics snapshot
- security posture summary
- recent GA or pilot reports when present
- signed support bundle manifest

## Bundle Requirements

- bundle content is redacted by default
- manifest is signed
- operator can verify manifest integrity after export
- bundle is suitable for offline transfer

## Expected Output

The export command returns:

- bundle directory
- zip archive path
- signed manifest path
- file count

Verify the manifest with:

```bash
uv run imperaos keys verify --profile enterprise --path <manifest_path> --json
```
