import os
import re
import random
from typing import Tuple, List, Optional, Dict

WILDCARD_TOKEN_RE = re.compile(r"__([A-Za-z0-9_\-]+)__")
# Matches the innermost {...} groups (no nested braces inside this match)
INNER_BRACE_RE = re.compile(r"\{([^{}]+)\}")

def split_choices(s: str) -> List[str]:
    """
    Split a choice string by top-level '|' (not inside nested braces).
    This is used *after* we've captured an innermost group, so nesting
    is not expected here. Still, we handle the simple case safely.
    """
    # Since this function is called on an *innermost* group (by regex),
    # there are no nested { } left inside `s`. So a plain split works.
    return [part.strip() for part in s.split("|")]

def find_first_top_level_brace(s: str) -> Optional[Tuple[int, int]]:
    """
    Return (start_index, end_index) of the first *top-level* { ... } in s,
    or None if none exist. Used for mirrored logic to identify the first
    brace segment that defines the primary choice list.
    """
    depth = 0
    start = None
    for i, ch in enumerate(s):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return (start, i)
    return None

class WildcardStore:
    def __init__(self, wildcard_dir: str):
        self.wildcard_dir = wildcard_dir
        self._cache: Dict[str, List[str]] = {}

    def load_lines(self, name: str) -> List[str]:
        """
        Loads wildcards from <wildcard_dir>/<name>.txt (cached).
        """
        if name in self._cache:
            return self._cache[name]

        path = os.path.join(self.wildcard_dir, f"{name}.txt")
        if not os.path.isfile(path):
            # Also allow "-" variants to look up 'foo-mir.txt'
            # (user can store mirrored lines in same-named file)
            raise FileNotFoundError(f"Wildcard file not found: {path}")

        lines: List[str] = []
        with open(path, "r", encoding="utf-8") as f:
            for raw in f.readlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                lines.append(line)
        self._cache[name] = lines
        return lines

class MirrorContext:
    """
    Holds mirrored selection state so positive/negative prompts
    get complementary picks consistently.
    """
    def __init__(self, rng: random.Random):
        self.rng = rng
        # key -> (num_choices, picked_index)
        self.memo: Dict[str, Tuple[int, int]] = {}

    def pick_index(self, key: str, num_choices: int, phase: str) -> int:
        """
        phase: 'pos' or 'neg'
        For pos: choose index and memoize. For neg: mirror the pos pick.
        Mirroring rule: mirrored = (num_choices - 1 - pos_index)
        """
        if phase not in ("pos", "neg"):
            phase = "pos"

        if key not in self.memo:
            # if this is negative first, still choose a base pick to mirror from
            pos_index = self.rng.randrange(num_choices)
            self.memo[key] = (num_choices, pos_index)

        n, pos_index = self.memo[key]
        if n != num_choices:
            # If inconsistent, clamp to current length
            pos_index = min(pos_index, num_choices - 1)

        if phase == "pos":
            return pos_index
        else:
            return max(0, num_choices - 1 - pos_index)

class PromptExpander:
    def __init__(self, wildcard_dir: str, seed: Optional[int] = None):
        self.wildcards = WildcardStore(wildcard_dir)
        self.rng = random.Random(seed if seed is not None else random.randint(0, 2**31-1))

    def expand_prompt(self, text: str, phase: str = "pos") -> str:
        """
        Expand a full prompt string, resolving mir/wildcards, and {…|…}.
        phase: 'pos' or 'neg' (used only for -mir logic)
        """
        mirror_ctx = MirrorContext(self.rng)
        return self._expand_all(text, mirror_ctx, phase)

    def _expand_all(self, s: str, mirror_ctx: MirrorContext, phase: str) -> str:
        # 1) Resolve all wildcard tokens (these may inject more braces)
        # Do multiple passes until there are no more wildcard tokens.
        safety_counter = 0
        while True:
            safety_counter += 1
            if safety_counter > 50:
                break  # prevent runaway replacements

            match = WILDCARD_TOKEN_RE.search(s)
            if not match:
                break

            token = match.group(1)  # e.g. hats or hats-mir
            is_mirrored = token.endswith("-mir")
            base_name = token[:-4] if is_mirrored else token

            # Pick a line from the wildcard file
            try:
                lines = self.wildcards.load_lines(base_name)
            except FileNotFoundError:
                # If missing, just strip the token
                replacement = ""
            else:
                choice_line = self.rng.choice(lines)

                if is_mirrored:
                    replacement = self._expand_mirrored_line(choice_line, base_name, mirror_ctx, phase)
                else:
                    # Ordinary wildcard: fully expand braces/wildcards in the chosen line
                    replacement = self._expand_choices_recursively(choice_line, mirror_ctx, phase)

            s = s[:match.start()] + replacement + s[match.end():]

        # 2) Expand any remaining brace choices in the original string
        s = self._expand_choices_recursively(s, mirror_ctx, phase)
        return s

    def _expand_choices_recursively(self, s: str, mirror_ctx: MirrorContext, phase: str) -> str:
        """
        Expand innermost {a|b|c} until none remain. Uses RNG for each group.
        """
        safety = 0
        while True:
            safety += 1
            if safety > 200:
                break
            m = INNER_BRACE_RE.search(s)
            if not m:
                break
            inner = m.group(1)
            options = split_choices(inner)
            if not options:
                chosen = ""
            else:
                chosen = self.rng.choice(options)
            s = s[:m.start()] + chosen + s[m.end():]
        return s

def _expand_mirrored_line(self, line: str, base_name: str, mirror_ctx: MirrorContext, phase: str) -> str:
    """
    Mirrored behavior:
      - Find the first top-level {a|b|c|...}.
      - Pick an index deterministically from MirrorContext.
      - POSITIVE: replace with the chosen option.
      - NEGATIVE: replace with a comma-separated list of all *other* options.
    Then expand remaining braces normally.
    If no brace exists, fall back to regular expansion.
    """
    pos = find_first_top_level_brace(line)
    if not pos:
        # No top-level brace; nothing to mirror—expand normally.
        return self._expand_choices_recursively(line, mirror_ctx, phase)

    start, end = pos
    inner = line[start+1:end]
    options = split_choices(inner)

    if not options:
        return self._expand_choices_recursively(line, mirror_ctx, phase)

    key = f"{base_name}:{line}"
    picked_idx = mirror_ctx.pick_index(key, len(options), "pos")  # always anchor on 'pos' choice

    if phase == "pos":
        replacement_core = options[picked_idx]
    else:
        # All remaining choices, comma-separated; if only one option exists, empty.
        remaining = [opt for i, opt in enumerate(options) if i != picked_idx]
        replacement_core = ", ".join(remaining).strip()

    rebuilt = line[:start] + replacement_core + line[end+1:]

    # Expand any remaining braces/wildcards after the mirrored substitution
    rebuilt = self._expand_choices_recursively(rebuilt, mirror_ctx, phase)
    return rebuilt

