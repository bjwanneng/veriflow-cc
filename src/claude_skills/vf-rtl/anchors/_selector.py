"""Anchor selector — maps module spec features to anchor directories.

Used by vf-coder in Stage 2 to pick the 1-2 most relevant anchors
for a given module.
"""

from pathlib import Path

ANCHORS_DIR = Path(__file__).parent


def select_anchors(module_spec: dict) -> list[Path]:
    """Return the 1-2 most relevant anchor directories for a module.

    Args:
        module_spec: dict from spec.json with optional "anchor_hints" list.

    Returns:
        List of Path objects pointing to anchor directories.
        Empty list if no hints match.
    """
    hints = module_spec.get("anchor_hints", [])
    return [ANCHORS_DIR / h for h in hints[:2]]


def select_anchors_by_features(
    module_type: str | None = None,
    has_states: bool = False,
    has_shift_register: bool = False,
    has_pipeline: bool = False,
    has_hash_round: bool = False,
    has_handshake: bool = False,
    handshake_mode: str = "hold_until_ack",
    has_variable_rotation: bool = False,
) -> list[Path]:
    """Heuristic anchor selection from module features.

    Rules (vf-architect uses these to generate anchor_hints):
      - control + has_states          -> fsm_4state
      - has_shift_register            -> shift_register
      - has_pipeline                  -> pipeline_register
      - has_hash_round                -> hash_round_one_cycle
      - has_handshake + hold_until_ack -> handshake_hold_until_ack
      - has_handshake + single_cycle  -> handshake_single_cycle
      - has_variable_rotation         -> barrel_shifter_var_n
    """
    hints = []
    if has_states or module_type == "control":
        hints.append("fsm_4state")
    if has_shift_register:
        hints.append("shift_register")
    if has_pipeline:
        hints.append("pipeline_register")
    if has_hash_round:
        hints.append("hash_round_one_cycle")
    if has_handshake:
        if handshake_mode == "single_cycle":
            hints.append("handshake_single_cycle")
        else:
            hints.append("handshake_hold_until_ack")
    if has_variable_rotation:
        hints.append("barrel_shifter_var_n")
    return [ANCHORS_DIR / h for h in hints[:2]]
