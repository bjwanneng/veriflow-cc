"""Anchor selector — maps module spec features to anchor directories.

Used by vf-coder in Stage 2 to pick the 1-2 most relevant anchors
for a given module.

Selection priority:
  1. explicit ``anchor_hints`` in module_spec (if provided by vf-spec-gen)
  2. auto-inferred from module ports / cycle_timing / timing_contract
  3. generic fallback (pipeline_register for data-path, fsm_4state for control)
"""

from pathlib import Path

ANCHORS_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Feature → anchor mapping
# ---------------------------------------------------------------------------

_ANCHOR_BY_FEATURE = {
    "has_states": "fsm_4state",
    "has_shift_register": "shift_register",
    "has_pipeline": "pipeline_register",
    "has_hash_round": "hash_round_one_cycle",
    "has_handshake_hold": "handshake_hold_until_ack",
    "has_handshake_pulse": "handshake_single_cycle",
    "has_variable_rotation": "barrel_shifter_var_n",
    "has_priority_encoder": "priority_encoder_8bit",
}

_PRIORITY_ORDER = [
    "has_hash_round",
    "has_handshake_hold",
    "has_handshake_pulse",
    "has_variable_rotation",
    "has_shift_register",
    "has_states",
    "has_pipeline",
    "has_priority_encoder",
]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def select_anchors(module_spec: dict) -> list[Path]:
    """Return the 1-2 most relevant anchor directories for a module.

    Args:
        module_spec: dict from spec.json with optional "anchor_hints" list.

    Returns:
        List of Path objects pointing to anchor directories.
    """
    # 1. Explicit hints (from spec.json if vf-spec-gen provided them)
    hints = module_spec.get("anchor_hints", [])
    matched = [_ensure_anchor_dir(h) for h in hints[:2] if _ensure_anchor_dir(h)]
    if matched:
        return matched

    # 2. Auto-infer from module description
    features = _infer_features(module_spec)
    matched = _match_features(features)
    if matched:
        return matched[:2]

    # 3. Generic fallback based on module_type
    module_type = module_spec.get("module_type", "")
    if module_type == "control":
        fallback = _ensure_anchor_dir("fsm_4state")
    else:
        fallback = _ensure_anchor_dir("pipeline_register")
    return [fallback] if fallback else []


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
    """Heuristic anchor selection from explicit feature flags.

    Rules (used to infer anchor_hints from module spec):
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
    return [_ensure_anchor_dir(h) for h in hints[:2] if _ensure_anchor_dir(h)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_anchor_dir(name: str) -> Path | None:
    """Return anchor dir path if it exists, else None."""
    p = ANCHORS_DIR / name
    return p if p.is_dir() else None


def _infer_features(module_spec: dict) -> dict[str, bool]:
    """Scan module_spec (ports, cycle_timing, timing_contract) for anchor-relevant features."""
    features: dict[str, bool] = {k: False for k in _ANCHOR_BY_FEATURE}
    ports = module_spec.get("ports", [])
    port_names = {p["name"] for p in ports}
    cycle_timing = module_spec.get("cycle_timing", {})
    timing_contract = module_spec.get("timing_contract", {})

    # FSM: has fsm_states in cycle_timing
    fsm_states = cycle_timing.get("fsm_states", [])
    if fsm_states and len(fsm_states) > 1:
        features["has_states"] = True

    # Shift register: has shift_en or shift-in/out ports
    if "shift_en" in port_names or {"shift_in", "shift_out"} & port_names:
        features["has_shift_register"] = True

    # Pipeline: multi-stage or valid-follows-data pattern
    pipeline = cycle_timing.get("pipeline_timing", {})
    latency = pipeline.get("input_to_output_latency_cycles", 0)
    if isinstance(latency, (int, float)) and latency >= 1:
        features["has_pipeline"] = True
    # Also detect from timing_contract.pipeline_delay_cycles
    delay = timing_contract.get("pipeline_delay_cycles", 0)
    if isinstance(delay, (int, float)) and delay >= 1:
        features["has_pipeline"] = True

    # Hash round: algorithm description mentions hash / round / compress
    desc = (module_spec.get("description", "") + " " + module_spec.get("module_name", "")).lower()
    if any(k in desc for k in ("hash", "round", "compress", "sha", "sm3")):
        features["has_hash_round"] = True

    # Handshake: valid + ack/ready ports
    has_valid = "valid" in port_names or "output_valid" in port_names
    has_ack = "ack" in port_names or "ready" in port_names
    if has_valid and has_ack:
        # Distinguish hold-until-ack vs single-cycle by signal_lifetime
        for p in ports:
            if p["name"] in ("valid", "output_valid"):
                lifetime = p.get("signal_lifetime", "")
                if lifetime == "pulse":
                    features["has_handshake_pulse"] = True
                else:
                    features["has_handshake_hold"] = True
                break
        if not features["has_handshake_pulse"] and not features["has_handshake_hold"]:
            # Default to hold-until-ack
            features["has_handshake_hold"] = True

    # Variable rotation: rotate/shift amount is a signal (not constant)
    if any(k in port_names for k in ("rotate_amount", "shift_amount", "rot_amt", "n")):
        features["has_variable_rotation"] = True
    if any("rotate" in p["name"] or "barrel" in desc for p in ports):
        features["has_variable_rotation"] = True

    # Priority encoder: encoded + valid output with single multi-bit input
    if "encoded" in port_names and "valid" in port_names:
        features["has_priority_encoder"] = True
    if "priority" in desc or "encoder" in desc:
        features["has_priority_encoder"] = True

    return features


def _match_features(features: dict[str, bool]) -> list[Path]:
    """Return anchor dirs for True features, ordered by priority."""
    matched: list[Path] = []
    for feat in _PRIORITY_ORDER:
        if features.get(feat):
            anchor_name = _ANCHOR_BY_FEATURE.get(feat)
            if anchor_name:
                p = _ensure_anchor_dir(anchor_name)
                if p and p not in matched:
                    matched.append(p)
    return matched
