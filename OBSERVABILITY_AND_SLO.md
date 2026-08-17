# Observability And SLO

Control Plane observability must make agent registry state, governed runs,
approval backlog, evidence verification and blocked claims visible without
opening a default network listener.

## Default Export Model

Enterprise deployments default to file-based observability.
No inbound metrics listener is enabled unless an operator explicitly turns it on.

Default outputs:

- `artifacts/metrics_snapshot.json`
- Prometheus textfile under the configured metrics directory

## Core Metric Families

- provider health and fallback rate
- completed, failed, blocked team jobs
- approval queue age and approval execution lag
- replay verify failure count
- audit inconsistency count
- fallback and serialization rate
- memory conflict reject rate
- runnable lag and task age
- operator and admin action counts
- backup, restore, and migration timestamps
- control-plane agents, runs, policy decisions, evidence verification failures and blocked claims

## Dashboard Views

- runtime health
- governance and approvals
- concurrency and conflict posture
- provider health
- storage and retention
- security and admin actions

## Incident Severity Mapping

- `SEV0`: replay verify failure, signature verify failure, unauthorized mutation, audit tamper
- `SEV1`: sustained runtime unavailable, restore failure, migration failure, provider chain unusable
- `SEV2`: elevated fallback/conflict rates or approval backlog
- `SEV3`: dashboard or reporting coverage gaps

## Initial SLO Targets

- replay verify pass rate: `100%`
- audit consistency error rate: `0`
- completed job integrity failures: `0`
- active primary provider health: `>= 99.5%` over rolling 24h
- fallback or serialization rate on reference workload: target `< 5%`, alert `> 10%`
- memory conflict reject rate on reference workload: target `< 2%`, alert `> 5%`

## Validation Rule

Observability is acceptable only if an operator can answer the following from the exported views without raw log spelunking:

- is the system safe?
- is it degraded?
- is it blocked?
- is the provider chain healthy?

## Command

```bash
uv run imperaos metrics snapshot --profile enterprise --json
```
