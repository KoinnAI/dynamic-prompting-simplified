import os
import re
import random
import hashlib
from typing import Tuple, List, Optional, Dict

# __token__ matches alnum, underscore, hyphen (so "hats-mir" is valid)
WILDCARD_TOKEN_RE = re.compile(r"__([A-Za-z0-9_\-]+)__")
# Innermost { ... } groups only (no nested braces inside this match)
INNER_BRACE_RE = re.compile(r"\{([^{}]+)\}")

def split_choices(s: str) -> List[str]:
    """Split a choice string by '|' and trim parts."""
    return [part.strip() for part in s.split("|")]

def find_first_top_level_brace(s: str) -> Optional[Tuple[int, int]]:
    """
    Return (start, end) index of the first *top-level* { ... } in s,
    or None if none exist.
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

def stable_pick_index(seed: int, key: str, num_choices: int) -> int:
    """
    Deterministically pick an index in [0, num_choices) based on (seed, key).
    Uses md5 to stay stable across Python versions.
    """
    if num_choices <= 0:
        return 0
    payload = f"{seed}::{key}".encode("utf-8")
    val = int(hashlib.md5(payload).hexdigest()[:8], 16)
    return val % num_choices

class WildcardStore:
    def __init__(self, wildcard_dir: str):
        self.wildcard_dir = wildcard_dir
        self._cache: Dict[str, List[str]] = {}

    def load_lines(self, name: str) -> List[str]:
        """
        Load <wildcard_dir>/<name>.txt (cached). 'name' is the exact token name,
        e.g. 'hats' or 'hats-mir'. We do NOT fallback between -mir and non-mir.
        """
        if name in self._cache:
            return self._cache[name]
        path = os.path.join(self.wildcard_dir, f"{name}.txt")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Wildcard file not found: {path}")
        lines: List[str] = []
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                lines.append(line)
        self._cache[name] = lines
        return lines

class PromptExpander:
    def __init__(self, wildcard_dir: str, seed: int = 0):
        self.wildcards = WildcardStore(wildcard_dir)
        self.seed = int(seed)
        # RNG used for non-mirrored random choices (brace expansion, non-mir wildcards)
        self.rng = random.Random(self.seed)

    def expand_prompt(self, text: str, phase: str = "pos") -> str:
        """
        Expand a full prompt string.
        phase: 'pos' or 'neg' (affects mirrored wildcard behavior only)
        """
        return self._expand_all(text or "", phase)

    def _expand_all(self, s: str, phase: str) -> str:
        """
        1) Resolve wildcard tokens (possibly injecting more braces/tokens)
        2) Expand remaining brace choices recursively
        Repeat until no tokens remain or safety cap is reached.
        """
        # Resolve wildcard tokens iteratively
        for _ in range(100):
            m = WILDCARD_TOKEN_RE.search(s)
            if not m:
                break

            token = m.group(1)  # e.g., "hats" or "ass-mir"
            is_mirrored = token.endswith("-mir")
            # IMPORTANT: -mir tokens read ONLY "<token>.txt" (no fallback)
            name_for_file = token if is_mirrored else token

            replacement = ""
            try:
                lines = self.wildcards.load_lines(name_for_file)
            except FileNotFoundError:
                # Missing wildcard: remove token silently
                replacement = ""
            else:
                # Deterministic line pick so pos/neg (and repeated runs) hit the same line
                line_idx = stable_pick_index(self.seed, f"{token}::line", len(lines))
                choice_line = lines[line_idx] if lines else ""

                if is_mirrored:
                    replacement = self._expand_mirrored_line(choice_line, token, phase)
                else:
                    # Regular wildcard: expand any braces inside that line
                    replacement = self._expand_choices_recursively(choice_line)

            s = s[:m.start()] + replacement + s[m.end():]

        # After wildcards are resolved (for now), expand remaining brace groups
        s = self._expand_choices_recursively(s)
        return s

    def _expand_choices_recursively(self, s: str) -> str:
        """
        Expand innermost {a|b|c} groups until none remain.
        Uses RNG for each group (non-deterministic across groups unless seed fixed).
        """
        for _ in range(400):
            m = INNER_BRACE_RE.search(s)
            if not m:
                break
            inner = m.group(1)
            options = split_choices(inner)
            chosen = self.rng.choice(options) if options else ""
            s = s[:m.start()] + chosen + s[m.end():]
        return s

    def _expand_mirrored_line(self, line: str, token_key: str, phase: str) -> str:
        """
        Mirrored wildcard behavior:
          - Locate the FIRST top-level {a|b|c|...} in the selected line.
          - Deterministically pick one option via (seed, token_key, line).
          - POSITIVE: replace that brace with the chosen option.
          - NEGATIVE: replace that brace with a comma-separated list of all remaining options.
          - Then expand any remaining braces in the rebuilt text.
        If the line has no top-level { }, we just expand braces normally.
        """
        pos = find_first_top_level_brace(line)
        if not pos:
            return self._expand_choices_recursively(line)

        start, end = pos
        inner = line[start+1:end]
        options = split_choices(inner)
        if not options:
            return self._expand_choices_recursively(line)

        idx = stable_pick_index(self.seed, f"{token_key}:{line}", len(options))

        if phase == "pos":
            core = options[idx]
        else:
            # Negative gets all options except the one used in positive
            others = [opt for i, opt in enumerate(options) if i != idx]
            core = ", ".join(others) if others else ""

        rebuilt = line[:start] + core + line[end+1:]
        return self._expand_choices_recursively(rebuilt)
