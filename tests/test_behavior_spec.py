"""Tests for behavior_spec.md and Stage 1 readiness check.

Validates:
1. spec.json no longer contains fsm_spec or data_flow_sequences
2. behavior_spec.md template has all required sections
3. readiness_check catches missing information
"""

import json
import os
import re
import tempfile
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helper: read the SKILL.md and extract the spec.json template
# ---------------------------------------------------------------------------

SKILL_PATH = Path(__file__).parent.parent / ".claude" / "skills" / "vf-pipeline" / "SKILL.md"


def _read_skill_md():
    return SKILL_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: spec.json schema should NOT contain fsm_spec or data_flow_sequences
# ---------------------------------------------------------------------------

def test_spec_json_has_no_fsm_spec():
    """fsm_spec should have been removed from spec.json template."""
    skill = _read_skill_md()
    # Find the spec.json template section
    spec_start = skill.find('"design_name": "design_name"')
    spec_end = skill.find("```", spec_start)
    spec_block = skill[spec_start:spec_end]

    # Try to parse the JSON template (after replacing template values)
    assert '"fsm_spec"' not in spec_block, (
        "fsm_spec should be removed from spec.json template — it belongs in behavior_spec.md"
    )


def test_spec_json_has_no_data_flow_sequences():
    """data_flow_sequences should have been removed from spec.json template."""
    skill = _read_skill_md()
    spec_start = skill.find('"design_name": "design_name"')
    spec_end = skill.find("```", spec_start)
    spec_block = skill[spec_start:spec_end]

    assert '"data_flow_sequences"' not in spec_block, (
        "data_flow_sequences should be removed from spec.json template — it belongs in behavior_spec.md"
    )


# ---------------------------------------------------------------------------
# Test 2: SKILL.md contains the new clarification sections E, F, G
# ---------------------------------------------------------------------------

def test_skill_has_timing_completeness_section():
    """Section E (Timing Completeness) must exist in Stage 1b."""
    skill = _read_skill_md()
    assert "E. Timing Completeness" in skill, (
        "Section E (Timing Completeness) is missing from Stage 1b"
    )
    assert "Cycle-level behavior" in skill or "Cycle-level" in skill


def test_skill_has_domain_knowledge_section():
    """Section F (Domain Knowledge) must exist in Stage 1b."""
    skill = _read_skill_md()
    assert "F. Domain Knowledge" in skill, (
        "Section F (Domain Knowledge) is missing from Stage 1b"
    )


def test_skill_has_info_completeness_section():
    """Section G (Information Completeness) must exist in Stage 1b."""
    skill = _read_skill_md()
    assert "G. Information Completeness" in skill, (
        "Section G (Information Completeness) is missing from Stage 1b"
    )


# ---------------------------------------------------------------------------
# Test 3: SKILL.md has the behavior_spec.md step and readiness check
# ---------------------------------------------------------------------------

def test_skill_has_behavior_spec_step():
    """Step 1c2 (Write behavior_spec.md) must exist."""
    skill = _read_skill_md()
    assert "1c2. Write behavior_spec.md" in skill, (
        "Step 1c2 (Write behavior_spec.md) is missing"
    )


def test_skill_has_readiness_check():
    """Step 1c3 (Readiness Check) must exist."""
    skill = _read_skill_md()
    assert "1c3. Readiness Check" in skill, (
        "Step 1c3 (Readiness Check gate) is missing"
    )
    assert "readiness_check" in skill.lower() or "Readiness Check" in skill


def test_skill_has_behavior_spec_template():
    """behavior_spec.md template must have all required sections."""
    skill = _read_skill_md()
    required_sections = [
        "Domain Knowledge",
        "Cycle-Accurate Behavior",
        "FSM Specification",
        "Register Requirements",
        "Timing Contracts",
        "Algorithm Pseudocode",
        "Protocol Details",
        "Cross-Module Timing",
    ]
    for section in required_sections:
        assert section in skill, (
            f"behavior_spec.md template is missing section: {section}"
        )


def test_skill_has_new_hook():
    """Hook should check both spec.json and behavior_spec.md."""
    skill = _read_skill_md()
    hook_start = skill.find("### 1d. Hook")
    hook_end = skill.find("### 1e.", hook_start)
    hook_block = skill[hook_start:hook_end]
    assert "behavior_spec.md" in hook_block, (
        "Hook should verify behavior_spec.md exists"
    )
    assert "Domain Knowledge" in hook_block, (
        "Hook should verify behavior_spec.md contains Domain Knowledge"
    )


# ---------------------------------------------------------------------------
# Test 4: vf-coder.md has BEHAVIOR_SPEC parameter
# ---------------------------------------------------------------------------

def test_coder_has_behavior_spec():
    """vf-coder agent must accept BEHAVIOR_SPEC parameter."""
    coder_path = Path(__file__).parent.parent / "claude_agents" / "vf-coder.md"
    coder = coder_path.read_text(encoding="utf-8")
    assert "BEHAVIOR_SPEC" in coder, (
        "vf-coder agent must accept BEHAVIOR_SPEC parameter"
    )
    assert "Step 2.5" in coder, (
        "vf-coder agent must have Step 2.5 to read behavior_spec.md"
    )
    # Must have 4 Reads + 1 Write
    assert "Read, Read, Read, Read, Write" in coder or "Read → Read → Read → Read → Write" in coder, (
        "vf-coder tool sequence must be Read×4 → Write (was Read×3 → Write)"
    )


# ---------------------------------------------------------------------------
# Test 5: SKILL.md skip rule has been replaced with confirm rule
# ---------------------------------------------------------------------------

def test_no_skip_section_rule():
    """The old 'skip that section entirely' rule should be removed."""
    skill = _read_skill_md()
    assert "skip that section entirely" not in skill, (
        "Old 'skip that section entirely' rule should be replaced with confirm rule"
    )


def test_has_confirm_rule():
    """New confirm rule must exist."""
    skill = _read_skill_md()
    assert "confirmed from input" in skill, (
        "New confirm rule should require explicit confirmation per item"
    )


# ---------------------------------------------------------------------------
# Test 6: Stage 2 reads behavior_spec.md
# ---------------------------------------------------------------------------

def test_stage2_reads_behavior_spec():
    """Stage 2 must list behavior_spec.md as input."""
    skill = _read_skill_md()
    stage2_start = skill.find("## Stage 2: microarch")
    stage2_end = skill.find("## Stage 3:", stage2_start)
    stage2_block = skill[stage2_start:stage2_end]
    assert "behavior_spec.md" in stage2_block, (
        "Stage 2 must read behavior_spec.md as input"
    )


# ---------------------------------------------------------------------------
# Test 7: Stage 4 coder prompt includes BEHAVIOR_SPEC
# ---------------------------------------------------------------------------

def test_stage4_prompt_includes_behavior_spec():
    """Stage 4 coder agent prompt must include BEHAVIOR_SPEC path."""
    skill = _read_skill_md()
    stage4_start = skill.find("## Stage 4: coder")
    stage4_end = skill.find("## Stage 5:", stage4_start)
    stage4_block = skill[stage4_start:stage4_end]
    assert "BEHAVIOR_SPEC" in stage4_block, (
        "Stage 4 coder prompt must include BEHAVIOR_SPEC"
    )
    assert "Read BEHAVIOR_SPEC" in stage4_block, (
        "Stage 4 coder prompt must instruct to Read BEHAVIOR_SPEC"
    )


# ---------------------------------------------------------------------------
# Test 8: Journal updated for behavior_spec.md
# ---------------------------------------------------------------------------

def test_journal_includes_behavior_spec():
    """Stage 1 journal should mention behavior_spec.md in outputs."""
    skill = _read_skill_md()
    journal_start = skill.find("### 1f. Journal")
    journal_end = skill.find("---", journal_start)
    journal_block = skill[journal_start:journal_end]
    assert "behavior_spec.md" in journal_block, (
        "Stage 1 journal should list behavior_spec.md in outputs"
    )


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [name for name, obj in sorted(globals().items())
             if name.startswith("test_") and callable(obj)]
    passed = 0
    failed = 0
    for name in tests:
        try:
            obj = globals()[name]
            obj()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    exit(1 if failed else 0)
