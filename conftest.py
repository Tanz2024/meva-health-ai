"""Root conftest.py — exists so pytest inserts the repository root onto
sys.path regardless of how it's invoked.

Several tests do `import scripts.release_check` to exercise
scripts/release_check.py's individual check functions directly.
`scripts/` is a plain directory (not installed as part of the `meva`
package), so it's only importable when the repository root is on
sys.path. `python -m pytest` adds the current working directory to
sys.path[0] automatically, but the `pytest` console-script entry point
(what CI and most contributors actually run) does not — this file makes
the behavior consistent either way, since pytest always inserts a root
conftest.py's own directory onto sys.path before collecting tests.
"""
