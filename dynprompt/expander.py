
import os
import re
import random
import hashlib
from typing import Tuple, List, Optional, Dict

WILDCARD_TOKEN_RE = re.compile(r"__([A-Za-z0-9_\-]+)__")
INNER_BRACE_RE = re.compile(r"\{([^{}]+)\}")

def split_choices(s: str) -> List[str]:
    return [part.strip() for part in s.split("|")]

def find_first_top_level_brace(s: str) -> Optional[Tuple[int, int]]:
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
    Uses md5 for stable hashing across runs.
    """
    payload = f"{seed}::{key}".encode("utf-8")
    digest = hashlib.md5(payload).hexdigest()
    # take 8 hex chars -> 32-bit int
    val = int(digest[:8], 16)
    return val % max(1, num_choices)

class WildcardStore:
    def __init__(self, wildcard_dir: str):
        self.wildcard_dir = wildcard_dir
        self._cache: Dict[str, List[str]] = {}

    def load_lines(self, name: str) -> List[str]:
        if name in self._cache:
            return self._cache[name]
        path = os.path.join(self.wildcard_dir, f"{name}.txt")
        if not os.path.isfile(path):
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

class PromptExpander:
    def __init__(self, wildcard_dir: str, seed: Optional[int] = None):
        self.wildcards = WildcardStore(wildcard_dir)
        self.seed = int(seed if seed is not None else 0)
        # RNG used for non-mirrored randoms only
        self.rng = random.Random(self.seed)

    def expand_prompt(self, text: str, phase: str = "pos") -> str:
        return self._expand_all(text, phase)

    def _expand_all(self, s: str, phase: str) -> str:
        safety_counter = 0
        # Resolve wildcard tokens iteratively
        while True:
            safety_counter += 1
            if safety_counter > 100:
                break
            match = WILDCARD_TOKEN_RE.search(s)
            if not match:
                break
            token = match.group(1)  # e.g., hats or hats-mir
            is_mirrored = token.endswith("-mir")
            base_name = token[:-4] if is_mirrored else token

            try:
                lines = self.wildcards.load_lines(base_name)
            except FileNotFoundError:
                replacement = ""
            else:
                choice_line = self.rng.choice(lines) if lines else ""
                if is_mirrored:
                    replacement = self._expand_mirrored_line(choice_line, base_name, phase)
                else:
                    replacement = self._expand_choices_recursively(choice_line)

            s = s[:match.start()] + replacement + s[match.end():]

        # Expand remaining braces
        s = self._expand_choices_recursively(s)
        return s

    def _expand_choices_recursively(self, s: str) -> str:
        safety = 0
        while True:
            safety += 1
            if safety > 400:
                break
            m = INNER_BRACE_RE.search(s)
            if not m:
                break
            inner = m.group(1)
            options = split_choices(inner)
            chosen = self.rng.choice(options) if options else ""
            s = s[:m.start()] + chosen + s[m.end():]
        return s

    def _expand_mirrored_line(self, line: str, base_name: str, phase: str) -> str:
        """
        Mirrored behavior:
          - Detect first top-level {a|b|c|...}
          - Pick a deterministic index via stable_pick_index(seed, key, n)
          - POS: replace with that option
          - NEG: replace with comma-separated list of ALL remaining options
          - Then expand other braces normally
        If no brace exists, fall back to regular expansion.
        """
        pos = find_first_top_level_brace(line)
        if not pos:
            return self._expand_choices_recursively(line)

        start, end = pos
        inner = line[start+1:end]
        options = split_choices(inner)
        if not options:
            return self._expand_choices_recursively(line)

        key = f"{base_name}:{line}"
        picked_idx = stable_pick_index(self.seed, key, len(options))

        if phase == "pos":
            replacement_core = options[picked_idx]
        else:
            remaining = [opt for i, opt in enumerate(options) if i != picked_idx]
            replacement_core = ", ".join(remaining).strip()

        rebuilt = line[:start] + replacement_core + line[end+1:]
        rebuilt = self._expand_choices_recursively(rebuilt)
        return rebuilt
