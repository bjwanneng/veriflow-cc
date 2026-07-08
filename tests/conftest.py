"""Pytest path bootstrap for the vf-rtl skill.

The *deployed* skill is flat: ``init.py`` writes ``PYTHONPATH=<skill root>``
so every tool imports siblings by bare name (``from rtl_utils import ...``).
The dashed skill name (``vf-rtl``) cannot be a Python package, so this flat
single-dir namespace is intentional - see CLAUDE.md.

In *source*, the ``.py`` tools are grouped into subdirs (``core/``, ``runners/``,
``analysis/``, ``verify/``, ``kb/``). For bare imports to resolve from source,
every subdir holding ``.py`` must be on ``sys.path``. This conftest adds the
skill root plus each such subdir, so tests work regardless of layout.

Forward-compatible: when the skill is still flat (no subdirs), the loop below
adds nothing extra and existing per-test ``sys.path.insert`` calls keep working.
"""
import sys
from pathlib import Path

_SKILL_ROOT = (
    Path(__file__).resolve().parent.parent
    / "src" / "claude_skills" / "vf-rtl"
)

# Subdirs that hold importable .py modules. templates/ and references/ are
# data dirs (no .py to import), so they are deliberately excluded.
_DATA_DIRS = {"templates", "references", "docs", "__pycache__"}

for _sub in sorted(_SKILL_ROOT.iterdir()):
    if _sub.is_dir() and _sub.name not in _DATA_DIRS:
        _p = str(_sub)
        if _p not in sys.path:
            sys.path.insert(0, _p)

# Skill root last (lowest priority) - subdirs win on name collisions, though
# none exist today.
_root = str(_SKILL_ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)
