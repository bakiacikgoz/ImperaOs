# RFC_COMPUTER_USE_002 Full Runtime Foundation

## Status
Accepted as the product-direction successor to the bounded browser pilot.

## Decision

ImperaOS is moving from operator-workflow parity plus bounded browser pilot toward:

> chat-first operator-grade AI workstation with full computer-use runtime ambitions

This does not authorize invisible autonomy. The runtime must remain:

- observable
- interruptible
- approval-aware
- replayable
- fail-closed

## Required Product Surfaces

### Chat workspace

- transcript-first interaction
- streamed state and progress
- attachments and context visibility
- approvals in-line with task progress
- artifacts and replay reachable from the same shell

### Computer-use runtime

- desktop/window control adapters
- browser adapters
- filesystem and dialog adapters
- clipboard and input primitives
- recovery, retry, checkpoint, resume

## Control Stack

1. Goal interpreter
2. Task planner
3. Environment perception layer
4. Action executor
5. Safety guard layer
6. State tracker / world model
7. Recorder / replay layer
8. Approval and interrupt layer
9. Recovery / retry engine

## Runtime Contract

Each control step should run in this order:

1. observe
2. interpret current state
3. compare against expected state
4. decide next action
5. classify risk
6. require approval if needed
7. execute
8. verify result
9. checkpoint
10. continue or recover

## World Model Minimum

The runtime should explicitly track:

- active application and window
- current objective and sub-goal
- last successful action
- pending approvals
- drift or unexpected user intervention
- changed resources and files
- checkpoint and replay references

## Delivery Guidance

- Keep the current browser pilot truthful in capability reporting.
- Add world-model and workspace foundations before claiming broad autonomy.
- Prefer scoped allow rules and visible approvals over permissive defaults.
