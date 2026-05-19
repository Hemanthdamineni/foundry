# Memory Architecture

Memory systems are post-MVP.

MVP state authority is SQLite. Latest checkpoints are recovery snapshots.
No vector memory, semantic memory, episodic memory, long-term learning, or
cross-task memory is required for implementation readiness.

Do not wire memory into phase prompts, validation, retry, checkpoint, or recovery
before the deterministic feature loop is complete.
