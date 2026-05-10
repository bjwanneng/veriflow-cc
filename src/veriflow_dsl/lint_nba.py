"""NBA Lint Hook — static checker for Verilog-2005 RTL.

Checks:
  L1: Sequential blocks (always @(posedge clk)) must use NBA (<=) only.
  L3: Module ports must align with spec.json.
  L4: Sequential blocks must not read _next/_new combinational wires.
  L5: Co-asserted enable signals must use independent if blocks, not if/else if.
  L6: case statements must include a default branch.
  L7: Concatenation width must match assignment target width.
  L8: always @(*) blocks with if-without-else may infer latches.
  L9: assign statements must not self-reference (combinational loop).
  L10: Internal wires must be driven by an assign or always block.

Usage:
    python -m veriflow_dsl.lint_nba <rtl_path> [<spec_path>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LintError:
    line: int
    rule: str
    message: str
    suggested_fix: str
    severity: str = "error"  # "error" or "warning"

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "rule": self.rule,
            "message": self.message,
            "suggested_fix": self.suggested_fix,
            "severity": self.severity,
        }


# ---------------------------------------------------------------------------
# L1: Sequential block must use NBA only
# ---------------------------------------------------------------------------

def _strip_comments(src: str) -> str:
    """Remove // and /* */ comments from Verilog source."""
    result = []
    i = 0
    while i < len(src):
        if src[i:i + 2] == "//":
            # Skip to end of line
            while i < len(src) and src[i] != "\n":
                i += 1
        elif src[i:i + 2] == "/*":
            i += 2
            while i + 1 < len(src) and src[i:i + 2] != "*/":
                i += 1
            i += 2
        else:
            result.append(src[i])
            i += 1
    return "".join(result)


_STRING_RE = re.compile(r'"[^"]*"')


def _strip_strings(line: str) -> str:
    """Replace double-quoted string literals with empty quotes."""
    return _STRING_RE.sub('""', line)


def _check_seq_only_nba(src: str) -> list[LintError]:
    """Find blocking assignments (=) inside sequential always blocks.

    Strategy: simple tokenizer tracking:
      - state: OUTSIDE / IN_SEQ_BLOCK / IN_COMB_BLOCK
      - begin/end depth
      - paren depth (to ignore = inside if/for/while conditions)
    """
    errors: list[LintError] = []
    clean_src = _strip_comments(src)
    lines = clean_src.split("\n")

    state = "OUTSIDE"  # OUTSIDE | IN_SEQ_BLOCK | IN_COMB_BLOCK
    begin_depth = 0
    paren_depth = 0

    for line_idx, raw_line in enumerate(lines):
        line_num = line_idx + 1
        line = raw_line.strip()

        # Detect always block start
        if line.startswith("always") and "@" in line:
            if "posedge" in line:
                state = "IN_SEQ_BLOCK"
                begin_depth = 0
            else:
                state = "IN_COMB_BLOCK"
                begin_depth = 0
            continue

        if state == "OUTSIDE":
            continue

        # Track paren depth for this line
        for ch in line:
            if ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth -= 1

        # Track begin/end depth
        # Strip string literals so "begin" / "end" inside $display args are not counted.
        line_no_strings = _strip_strings(line)
        begin_count = len(re.findall(r'\bbegin\b', line_no_strings))
        end_count = len(re.findall(r'\bend\b', line_no_strings))
        begin_depth += begin_count - end_count

        # If we've exited the block, return to OUTSIDE
        if begin_depth < 0:
            state = "OUTSIDE"
            begin_depth = 0
            paren_depth = 0
            continue

        # Only check sequential blocks
        if state != "IN_SEQ_BLOCK":
            continue

        # Look for blocking assignment '=' that is not part of:
        #   <=  (NBA or comparison)
        #   ==  (equality)
        #   !=  (inequality)
        #   >=  (greater-equal)
        #   +=  -= *= /= %= (compound assignment — also blocking, should flag)
        #   === !== (4-state equality — unlikely but safe to ignore)
        # Also skip if inside parentheses (if/while/for condition)
        if paren_depth > 0:
            continue

        # Find all '=' positions in the line
        for match in re.finditer(r'=', line):
            pos = match.start()
            prev_char = line[pos - 1] if pos > 0 else ""
            next_char = line[pos + 1] if pos < len(line) - 1 else ""

            # Skip if part of: <=  ==  !=  >=  ===  !==
            if prev_char in "<!=>" or next_char in "<=>":
                continue

            if prev_char in "+-*/%":
                errors.append(
                    LintError(
                        line=line_num,
                        rule="L1_seq_only_nba",
                        message=f"Compound blocking assignment '{prev_char}=' found in sequential block. Use NBA (<=) instead.",
                        suggested_fix=f"Replace '{prev_char}=' with '<='.",
                    )
                )
                continue

            errors.append(
                LintError(
                    line=line_num,
                    rule="L1_seq_only_nba",
                    message="Blocking assignment '=' found in sequential block. Use NBA (<=) instead.",
                    suggested_fix="Replace '=' with '<='.",
                )
            )

    return errors


# ---------------------------------------------------------------------------
# L3: Port alignment
# ---------------------------------------------------------------------------

def _extract_verilog_ports(src: str) -> dict[str, dict]:
    """Parse Verilog module declaration and return port info.

    Returns:
        {port_name: {"direction": "input"|"output", "width": int|None}}
        width is None for parameterized expressions (e.g. [DATA_WIDTH-1:0]).
    """
    ports: dict[str, dict] = {}

    # Match port declarations like:
    #   input  wire [7:0] port_name
    #   output wire [DATA_WIDTH-1:0] port_name
    #   input  wire       clk
    pattern = re.compile(
        r'(input|output)\s+(?:wire|reg)?\s*(?:\[([^\]]+)\])?\s*(\w+)',
        re.IGNORECASE,
    )

    for match in pattern.finditer(src):
        direction = match.group(1).lower()
        width_str = match.group(2)
        name = match.group(3)

        # Try to parse as [N:0] — simple numeric width
        if width_str:
            m = re.match(r'(\d+)\s*:\s*0', width_str)
            width = int(m.group(1)) + 1 if m else None
        else:
            width = 1
        ports[name] = {"direction": direction, "width": width}

    return ports


def _check_port_alignment(src: str, spec_module: dict) -> list[LintError]:
    """Compare Verilog ports against spec.json module definition."""
    errors: list[LintError] = []

    rtl_ports = _extract_verilog_ports(src)
    spec_ports = {
        p["name"]: {
            "direction": p.get("direction", "input").lower(),
            "width": p.get("width", 1),
        }
        for p in spec_module.get("ports", [])
    }

    # Missing ports: spec has but RTL doesn't
    for name, spec_info in spec_ports.items():
        if name not in rtl_ports:
            errors.append(
                LintError(
                    line=0,
                    rule="L3_port_align",
                    message=f"Missing port '{name}' in RTL (expected {spec_info['direction']} [{spec_info['width']-1}:0]).",
                    suggested_fix=f"Add '{name}' to the module port list.",
                )
            )

    # Extra ports: RTL has but spec doesn't
    for name, rtl_info in rtl_ports.items():
        if name not in spec_ports:
            errors.append(
                LintError(
                    line=0,
                    rule="L3_port_align",
                    message=f"Extra port '{name}' in RTL not found in spec.",
                    suggested_fix=f"Remove '{name}' from the module port list or add it to spec.json.",
                )
            )

    # Mismatched direction or width
    for name in set(rtl_ports) & set(spec_ports):
        rtl_info = rtl_ports[name]
        spec_info = spec_ports[name]

        if rtl_info["direction"] != spec_info["direction"]:
            errors.append(
                LintError(
                    line=0,
                    rule="L3_port_align",
                    message=(
                        f"Port '{name}' direction mismatch: "
                        f"RTL='{rtl_info['direction']}', spec='{spec_info['direction']}'."
                    ),
                    suggested_fix=f"Change direction to '{spec_info['direction']}'.",
                )
            )

        if rtl_info["width"] is not None and spec_info["width"] is not None:
            if rtl_info["width"] != spec_info["width"]:
                errors.append(
                    LintError(
                        line=0,
                        rule="L3_port_align",
                        message=(
                            f"Port '{name}' width mismatch: "
                            f"RTL={rtl_info['width']}, spec={spec_info['width']}."
                        ),
                        suggested_fix=f"Adjust width to [{spec_info['width']-1}:0].",
                    )
                )

    return errors


# ---------------------------------------------------------------------------
# L4: Sequential block must not read _next/_new combinational wires
# ---------------------------------------------------------------------------

_NEXT_NEW_RE = re.compile(r'\b(\w+(?:_next|_new|_n))\b')


def _check_finalize_reads_next(src: str) -> list[LintError]:
    """Flag _next/_new reads inside always @(posedge clk) blocks.

    Pattern: x_reg <= some_expr_next — using a combinational _next wire
    in a sequential block, which is the finalize-state bug pattern.

    The CORRECT pattern is: x_reg <= x_next (reading the _next that
    corresponds to x_reg). The BUG pattern is: x_reg <= y_next where
    y_next is NOT the _next of x_reg.

    Simplified check: flag any _next/_new signal on the RHS of <= in a
    sequential block, UNLESS it's the direct _next of the target register
    (e.g., acc_reg <= acc_next is OK, but result_reg <= acc_next is suspicious).
    """
    errors: list[LintError] = []
    clean_src = _strip_comments(src)
    lines = clean_src.split("\n")

    state = "OUTSIDE"
    begin_depth = 0

    for line_idx, raw_line in enumerate(lines):
        line_num = line_idx + 1
        line = raw_line.strip()

        if line.startswith("always") and "@" in line:
            if "posedge" in line:
                state = "IN_SEQ_BLOCK"
                begin_depth = 0
            else:
                state = "IN_COMB_BLOCK"
                begin_depth = 0
            continue

        if state != "IN_SEQ_BLOCK":
            line_no_strings = _strip_strings(line)
            begin_depth += len(re.findall(r'\bbegin\b', line_no_strings)) - \
                          len(re.findall(r'\bend\b', line_no_strings))
            if begin_depth < 0:
                state = "OUTSIDE"
                begin_depth = 0
            continue

        line_no_strings = _strip_strings(line)
        begin_depth += len(re.findall(r'\bbegin\b', line_no_strings)) - \
                      len(re.findall(r'\bend\b', line_no_strings))

        if begin_depth < 0:
            state = "OUTSIDE"
            begin_depth = 0
            continue

        # Look for <= assignments with _next/_new on RHS
        nba_match = re.match(r'\s*(\w+)\s*<=\s*(.*)', line_no_strings)
        if not nba_match:
            continue

        target = nba_match.group(1)
        rhs = nba_match.group(2)

        for m in _NEXT_NEW_RE.finditer(rhs):
            name = m.group(1)
            # Check if this _next is the direct next of the target
            # e.g., acc_reg <= acc_next is OK (acc_next is next of acc_reg)
            # Strip _next/_new suffix and compare with target stripped of _reg
            base_name = re.sub(r'_(?:next|new|n)$', '', name)
            target_base = re.sub(r'_reg$', '', target)
            if base_name != target_base:
                errors.append(
                    LintError(
                        line=line_num,
                        rule="L4_finalize_reads_next",
                        message=f"Sequential block reads combinational wire '{name}' into '{target}' — potential extra-round bug in finalize state.",
                        suggested_fix=f"Replace '{name}' with the registered version or verify this is intentional.",
                        severity="warning",
                    )
                )
                break  # one error per line

    return errors


# ---------------------------------------------------------------------------
# L5: Co-asserted enable signals must use independent if blocks
# ---------------------------------------------------------------------------

_EN_KEYWORDS = re.compile(r'\b\w*(?:_en|_valid|_load|_enable|_start|_done)\b')
_IF_RE = re.compile(r'\bif\s*\(')
_ELIF_RE = re.compile(r'\belse\s+if\s*\(')


def _check_coasserted_if_elif(src: str) -> list[LintError]:
    """Flag if/else if chains where both conditions contain enable-like signals.

    LLMs often use if/else if for signals that are co-asserted (both true
    in the same cycle), causing only the first branch to execute.
    """
    errors: list[LintError] = []
    clean_src = _strip_comments(src)
    lines = clean_src.split("\n")

    in_comb = False
    begin_depth = 0
    prev_if_had_enable = False
    prev_if_depth = -1  # begin_depth BEFORE the if (so else if at same level is caught)

    for line_idx, raw_line in enumerate(lines):
        line_num = line_idx + 1
        line = raw_line.strip()

        if line.startswith("always") and "@" in line:
            if "posedge" not in line:
                in_comb = True
                begin_depth = 0
                line_no_strings = _strip_strings(line)
                begin_depth += len(re.findall(r'\bbegin\b', line_no_strings)) - \
                              len(re.findall(r'\bend\b', line_no_strings))
            else:
                in_comb = False
            continue

        if not in_comb:
            continue

        line_no_strings = _strip_strings(line)
        depth_before = begin_depth
        begin_depth += len(re.findall(r'\bbegin\b', line_no_strings)) - \
                      len(re.findall(r'\bend\b', line_no_strings))

        if begin_depth < 0:
            in_comb = False
            begin_depth = 0
            prev_if_had_enable = False
            continue

        # Reset prev_if when we've closed the scope that contained it
        if prev_if_depth >= 0 and depth_before < prev_if_depth:
            prev_if_had_enable = False
            prev_if_depth = -1

        # Detect "else if" with enable keyword
        elif_match = _ELIF_RE.search(line_no_strings)
        if elif_match and prev_if_had_enable:
            if _EN_KEYWORDS.search(line_no_strings):
                errors.append(
                    LintError(
                        line=line_num,
                        rule="L5_coasserted_if_elif",
                        message="else if with enable-like signal after another if with enable — these may be co-asserted and should use independent if blocks.",
                        suggested_fix=f"Change 'else if' on line {line_num} to 'if' (independent block).",
                    )
                )

        # Track if this line is an if with enable keyword
        if_match = _IF_RE.search(line_no_strings)
        if if_match:
            prev_if_had_enable = bool(_EN_KEYWORDS.search(line_no_strings))
            if prev_if_had_enable:
                prev_if_depth = depth_before

    return errors


# ---------------------------------------------------------------------------
# L6: case statements must include default branch
# ---------------------------------------------------------------------------

def _check_missing_default(src: str) -> list[LintError]:
    """Flag case statements without a default branch (latch risk)."""
    errors: list[LintError] = []
    clean_src = _strip_comments(src)
    lines = clean_src.split("\n")

    in_case = False
    case_start = 0
    has_default = False
    case_depth = 0

    for line_idx, raw_line in enumerate(lines):
        line_num = line_idx + 1
        line = raw_line.strip()

        # Detect case start
        if re.match(r'\bcase\s*\(', line):
            in_case = True
            case_start = line_num
            has_default = False
            case_depth = 0
            continue

        if not in_case:
            continue

        if re.match(r'\bendcase\b', line):
            if not has_default:
                errors.append(
                    LintError(
                        line=case_start,
                        rule="L6_missing_default",
                        message=f"case statement starting at line {case_start} has no default branch — may infer latches.",
                        suggested_fix="Add 'default: ;' before endcase.",
                    )
                )
            in_case = False
            continue

        if re.match(r'\bdefault\s*:', line):
            has_default = True

    return errors


# ---------------------------------------------------------------------------
# L7: Concatenation width must match assignment target
# ---------------------------------------------------------------------------

_WIDTH_DECL_RE = re.compile(r'\[(\d+):0\]')
_CONCAT_RE = re.compile(r'\{([^}]+)\}')
_SLICE_RE = re.compile(r'\[(\d+):(\d+)\]')


def _check_concat_width(src: str) -> list[LintError]:
    """Flag {a, b} concatenations where summed widths don't match target.

    Catches ROL bit-slice errors like {x[22:0], x[31:7]} (23+25=48 ≠ 32).
    """
    errors: list[LintError] = []
    clean_src = _strip_comments(src)
    lines = clean_src.split("\n")

    for line_idx, raw_line in enumerate(lines):
        line_num = line_idx + 1
        line = raw_line.strip()

        # Look for lines with both a target width declaration and concatenation
        # Pattern: [N:0] signal_name = ... { ... }
        # or:     wire [N:0] signal_name = { ... }
        # or:     assign signal_name = { ... } where signal was declared [N:0]
        concats = list(_CONCAT_RE.finditer(line))
        if not concats:
            continue

        # Find target width from this line or context
        target_width = None

        # Try to find [N:0] on the LHS of assignment
        assign_pos = line.find("<=")
        if assign_pos == -1:
            assign_pos = line.find("=")
        if assign_pos == -1:
            assign_pos = line.find("assign")

        if assign_pos > 0:
            lhs = line[:assign_pos]
            width_match = _WIDTH_DECL_RE.search(lhs)
            if width_match:
                target_width = int(width_match.group(1)) + 1

        if target_width is None:
            continue  # Can't determine target width

        for concat_match in concats:
            inner = concat_match.group(1)
            # Sum widths of each part in the concatenation
            parts = [p.strip() for p in inner.split(",")]
            total_bits = 0
            known = True

            for part in parts:
                # Check for explicit slice [H:L]
                slice_match = _SLICE_RE.search(part)
                if slice_match:
                    high = int(slice_match.group(1))
                    low = int(slice_match.group(2))
                    total_bits += high - low + 1
                elif re.match(r"^\d+$", part):
                    total_bits += 32  # unsized integer
                    known = False
                else:
                    # Plain signal — width unknown from this line alone
                    known = False
                    total_bits += 1  # assume 1 bit minimum

            if known and total_bits != target_width:
                errors.append(
                    LintError(
                        line=line_num,
                        rule="L7_concat_width",
                        message=f"Concatenation width ({total_bits} bits) != target width ({target_width} bits) — likely ROL/ROR bit-slice error.",
                        suggested_fix=f"Adjust slice widths so they sum to {target_width}.",
                    )
                )

    return errors


# ---------------------------------------------------------------------------
# L8: Latch detection — incomplete assignments in always @(*)
# ---------------------------------------------------------------------------


def _check_latch_from_incomplete_assign(src: str) -> list[LintError]:
    """Flag always @(*) blocks where an if lacks an else (latch risk).

    Simplified heuristic: inside an always @(*) block, any if statement
    that does not have a matching else branch at the same begin/end level
    is flagged.  This catches the most common LLM latch bug.
    """
    errors: list[LintError] = []
    clean_src = _strip_comments(src)
    lines = clean_src.split("\n")

    in_comb = False
    begin_depth = 0
    # Stack of (depth_when_if_seen, line_num, has_else) for open ifs
    if_stack: list[tuple[int, int, bool]] = []

    for line_idx, raw_line in enumerate(lines):
        line_num = line_idx + 1
        line = raw_line.strip()

        # Detect always block start
        if line.startswith("always") and "@" in line:
            in_comb = "posedge" not in line
            begin_depth = 0
            if_stack = []
            continue

        if not in_comb:
            continue

        line_no_strings = _strip_strings(line)
        # Track begin/end depth
        begin_count = len(re.findall(r'\bbegin\b', line_no_strings))
        end_count = len(re.findall(r'\bend\b', line_no_strings))
        depth_before = begin_depth
        begin_depth += begin_count - end_count

        # Pop ifs that were closed by end (depth strictly greater than current)
        while if_stack and if_stack[-1][0] > begin_depth:
            depth, if_line, has_else = if_stack.pop()
            if not has_else:
                errors.append(
                    LintError(
                        line=if_line,
                        rule="L8_latch_detect",
                        message=f"if statement at line {if_line} in always @(*) has no else — may infer a latch.",
                        suggested_fix="Add an else branch or default assignment to avoid latch inference.",
                        severity="warning",
                    )
                )

        if begin_depth < 0:
            # Block ended — report any remaining unclosed ifs before reset
            while if_stack:
                depth, if_line, has_else = if_stack.pop()
                if not has_else:
                    errors.append(
                        LintError(
                            line=if_line,
                            rule="L8_latch_detect",
                            message=f"if statement at line {if_line} in always @(*) has no else — may infer a latch.",
                            suggested_fix="Add an else branch or default assignment to avoid latch inference.",
                            severity="warning",
                        )
                    )
            in_comb = False
            begin_depth = 0
            continue

        # Detect if / else if / else
        if re.search(r'\bif\s*\(', line_no_strings):
            if_stack.append((begin_depth, line_num, False))
        elif re.search(r'\belse\s+if\s*\(', line_no_strings):
            # Convert previous if to "has_else=True" (it's chained)
            if if_stack and if_stack[-1][0] == depth_before:
                d, ln, _ = if_stack.pop()
                if_stack.append((d, ln, True))
            # Also push a new if frame
            if_stack.append((begin_depth, line_num, False))
        elif re.search(r'\belse\b', line_no_strings):
            if if_stack and if_stack[-1][0] == depth_before:
                d, ln, _ = if_stack.pop()
                if_stack.append((d, ln, True))

    return errors


# ---------------------------------------------------------------------------
# L9: Combinational loop detection
# ---------------------------------------------------------------------------

_ASSIGN_RE = re.compile(r'assign\s+(\w+)\s*=\s*(.*);')


def _check_combinational_loop(src: str) -> list[LintError]:
    """Flag assign statements where LHS appears on RHS (self-reference)."""
    errors: list[LintError] = []
    clean_src = _strip_comments(src)
    lines = clean_src.split("\n")

    for line_idx, raw_line in enumerate(lines):
        line_num = line_idx + 1
        line = raw_line.strip()
        m = _ASSIGN_RE.match(line)
        if not m:
            continue
        lhs = m.group(1)
        rhs = m.group(2)
        # Check if lhs name appears as a whole-word in rhs
        if re.search(r'\b' + re.escape(lhs) + r'\b', rhs):
            errors.append(
                LintError(
                    line=line_num,
                    rule="L9_comb_loop",
                    message=f"Combinational loop: '{lhs}' assigned from an expression that references '{lhs}'.",
                    suggested_fix="Break the loop with a register (posedge clk) or restructure logic.",
                )
            )

    return errors


# ---------------------------------------------------------------------------
# L10: Undriven wire detection
# ---------------------------------------------------------------------------

_WIRE_DECL_RE = re.compile(r'\bwire\s+(?:\[([^\]]+)\]\s+)?(\w+)')
_ASSIGN_LHS_RE = re.compile(r'assign\s+(\w+)\s*=')
_ALWAYS_LHS_RE = re.compile(r'\b(\w+)\s*(?:<=|=)\s*')


def _check_undriven_wire(src: str) -> list[LintError]:
    """Flag internal wires that are declared but never assigned."""
    errors: list[LintError] = []
    clean_src = _strip_comments(src)
    lines = clean_src.split("\n")

    # Collect declared wires (excluding ports — handled by direction)
    wires: set[str] = set()
    inputs: set[str] = set()

    for line in lines:
        # Input ports are driven externally
        m = re.match(r'\s*input\s+(?:wire\s+)?(?:\[[^\]]+\]\s+)?(\w+)', line)
        if m:
            inputs.add(m.group(1))
            continue

        # Wire declarations inside module body
        for m in _WIRE_DECL_RE.finditer(line):
            wires.add(m.group(2))

    # Collect assigned signals
    driven: set[str] = set()
    for line in lines:
        # assign lhs = ...
        for m in _ASSIGN_LHS_RE.finditer(line):
            driven.add(m.group(1))
        # always block lhs
        for m in _ALWAYS_LHS_RE.finditer(line):
            driven.add(m.group(1))

    # Wires that are never driven (and not inputs)
    for w in wires:
        if w not in driven and w not in inputs:
            errors.append(
                LintError(
                    line=0,
                    rule="L10_undriven_wire",
                    message=f"Wire '{w}' is declared but never driven.",
                    suggested_fix=f"Add an assign statement driving '{w}', or remove the declaration.",
                    severity="warning",
                )
            )

    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lint_module_v(rtl_path: Path, spec_module: dict | None = None) -> list[LintError]:
    """Run all lint checks on a single Verilog file.

    Args:
        rtl_path: Path to the Verilog file.
        spec_module: Optional spec.json module dict for L3 port alignment.

    Returns:
        Empty list = pass; non-empty = list of LintError.
    """
    rtl_path = Path(rtl_path) if not isinstance(rtl_path, Path) else rtl_path
    src = rtl_path.read_text()
    errors: list[LintError] = []

    errors.extend(_check_seq_only_nba(src))
    errors.extend(_check_finalize_reads_next(src))
    errors.extend(_check_coasserted_if_elif(src))
    errors.extend(_check_missing_default(src))
    errors.extend(_check_concat_width(src))
    errors.extend(_check_latch_from_incomplete_assign(src))
    errors.extend(_check_combinational_loop(src))
    errors.extend(_check_undriven_wire(src))

    if spec_module is not None:
        errors.extend(_check_port_alignment(src, spec_module))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="NBA Lint Hook for VeriFlow RTL")
    parser.add_argument("rtl_path", help="Path to Verilog file")
    parser.add_argument("spec_path", nargs="?", help="Path to spec.json (optional, for L3)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    args = parser.parse_args()

    rtl_path = Path(args.rtl_path)
    if not rtl_path.exists():
        print(f"Error: RTL file not found: {rtl_path}", file=sys.stderr)
        return 2

    spec_module = None
    if args.spec_path:
        spec_path = Path(args.spec_path)
        if spec_path.exists():
            try:
                with open(spec_path) as f:
                    data = json.load(f)
                # spec.json may be a single module dict or a list of modules
                if isinstance(data, list):
                    # Try to find matching module by filename stem
                    target_name = rtl_path.stem
                    for mod in data:
                        if mod.get("name") == target_name:
                            spec_module = mod
                            break
                else:
                    spec_module = data
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in {spec_path}: {e}", file=sys.stderr)
                return 2

    errors = lint_module_v(rtl_path, spec_module)

    if args.json:
        print(json.dumps([e.to_dict() for e in errors], indent=2))
    else:
        if not errors:
            print("PASS: No NBA lint errors found.")
        else:
            warnings = [e for e in errors if e.severity == "warning"]
            hard_errors = [e for e in errors if e.severity != "warning"]
            if hard_errors:
                print(f"FAIL: {len(hard_errors)} NBA lint error(s) found:")
                for e in hard_errors:
                    print(f"  Line {e.line:3} [{e.rule}] {e.message}")
                    print(f"           Fix: {e.suggested_fix}")
            if warnings:
                print(f"WARNING: {len(warnings)} NBA lint warning(s):")
                for e in warnings:
                    print(f"  Line {e.line:3} [{e.rule}] {e.message}")
                    print(f"           Fix: {e.suggested_fix}")

    has_errors = any(e.severity != "warning" for e in errors)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
