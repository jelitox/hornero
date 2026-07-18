# TASK-077: Changelog and release-note visibility
**Feature**: SPEC-008 | **Status**: done | **Priority**: high | **Depends-on**: TASK-076

Add typed changelog fragments, deterministic validation and preview commands,
a pull-request policy check, exact per-build PyPI release summaries, metadata
links, contributor documentation and regression tests.

**Completion**: Pull requests record reviewable change fragments, PyPI builds
show their exact source delta, and repository/PyPI changelog links are visible.

**Deviation**: Full-gate verification exposed a pre-existing concurrent SQLite
WAL initialization race. TASK-077 includes a bounded retry and regression gate
so release CI remains deterministic.
