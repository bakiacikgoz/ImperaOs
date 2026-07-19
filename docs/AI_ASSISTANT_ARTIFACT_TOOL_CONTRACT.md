# AI Assistant Artifact Tool Contract

The model-visible artifact tool surface is exactly:

- `artifact.create_draft`
- `artifact.get_context`
- `artifact.propose_mutation`
- `artifact.request_form`
- `artifact.request_export`

Every input is validated by a strict Pydantic model. Unknown fields, unknown `artifact.*`
tool names, unsupported mutation types, unsafe form schemas, stale revisions, and policy
denials fail closed in the trusted Python boundary.

`artifact.get_context` returns an exact-revision, purpose-bound context pack. Without a
selection it returns metadata only. With a selection it contains only the requested
coordinate/opaque-ID projection, is redacted, classified, SHA-256 bound, and limited to
32 KiB / 8,192 estimated tokens.

`artifact.propose_mutation` never applies content. It persists the full request hash,
context and selection hashes, source session/turn/trace provenance, and creates an
approval ticket bound to the exact workspace, artifact, proposal, action hash and
executor. Applying the proposal is model-hidden and requires the backend to atomically
claim and consume that verified approval.

`artifact.request_export` validates the exact artifact revision and allowed format but
does not begin a native write. It emits a hash-bound `confirmation_required` request;
the user-facing native export flow remains responsible for confirmation, preflight,
ticket validation and atomic write.

The following are explicitly model-hidden and denied: direct apply, arbitrary file
write, renderer-supplied asset paths, code execution, permanent deletion, external send,
and export commit. Provider-native/server tools remain denied by the existing provider
tool policy.
