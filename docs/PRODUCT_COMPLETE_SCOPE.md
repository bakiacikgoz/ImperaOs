# Product-Complete Scope

ImperaOS / ImperaOS product-complete status means a self-hosted, single-organization
enterprise Agent Control Plane that can be installed locally, connected to a real
assistant runtime or explicit setup diagnostic, and verified by release gates.

In scope:

- Real AI Assistant runtime bridge or setup-required diagnostic.
- Operator Panel real bridge parity with preview mode clearly separated.
- Enterprise workspace, identity, RBAC, agent enrollment, governed run, approval,
  evidence, memory, and support bundle workflows.
- First-run setup and internal desktop readiness evidence.
- Product-complete closure gate with no-ship blockers.

Out of scope:

- Public cloud multi-tenant SaaS.
- Unrestricted live desktop automation.
- Production SSO/LDAP/Active Directory sync.
- Public signed desktop release without real signing and notarization evidence.
- External customer pilot execution.

Every visible product capability must be one of:

- `working`: backed by real CLI/bridge behavior.
- `disabled_with_reason`: blocked with a visible reason code and next action.
- `preview_only`: visible only in explicit preview/dev mode.
