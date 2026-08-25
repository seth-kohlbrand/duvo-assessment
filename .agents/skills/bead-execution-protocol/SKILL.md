---
name: bead-execution-protocol
description: Execute work items explicitly tracked as beads with dependency checks, scoped implementation, verification, and concise completion evidence.
---

# Bead Execution Protocol

Use this workflow only when a task is explicitly tracked as a bead.

1. Read the bead, acceptance criteria, dependencies, and applicable repository instructions.
2. Inspect the worktree and preserve unrelated changes.
3. Confirm affected interfaces, data paths, permissions, and failure modes before editing.
4. Implement the smallest complete change using established repository patterns.
5. Run the bead's required checks plus focused tests for changed behavior.
6. Exercise state-changing behavior through the real write and read paths; do not treat optimistic UI, a toast, or compilation as persistence proof.

Report the behavior changed, important files or contracts, commands actually run, outcomes, and unresolved risks. Do not claim completion while required checks fail.
