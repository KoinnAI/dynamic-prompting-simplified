
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
    payload = f"{seed}::{key}".encode("utf-8")
    val = int(hashlib.md5(payload).hexdigest()[:8], 16)
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
    def __init__(self, wildcard_dir: str, seed: int = 0):
        self.wildcards = WildcardStore(wildcard_dir)
        self.seed = int(seed)
        self.rng = random.Random(self.seed)

    def expand_prompt(self, text: str, phase: str = "pos") -> str:
        return self._expand_all(text, phase)

    def _expand_all(self, s: str, phase: str) -> str:
        # Resolve wildcard tokens iteratively (they may inject new braces)
        for _ in range(100):
            m = WILDCARD_TOKEN_RE.search(s)
            if not m:
                break
            token = m.group(1)
            is_mirrored = token.endswith("-mir")
            base_name = token[:-4] if is_mirrored else token
            try:
                lines = self.wildcards.load_lines(base_name)
            except FileNotFoundError:
                replacement = ""
            else:
                line = self.rng.choice(lines) if lines else ""
                replacement = (
                    self._expand_mirrored_line(line, base_name, phase)
                    if is_mirrored else
                    self._expand_choices_recursively(line)
                )
            s = s[:m.start()] + replacement + s[m.end():]
        # Expand remaining braces
        s = self._expand_choices_recursively(s)
        return s

    def _expand_choices_recursively(self, s: str) -> str:
        for _ in range(400):
            m = INNER_BRACE_RE.search(s)
            if not m:
                break
            inner = m.group(1)
            options = split_choices(inner)
            chosen = self.rng.choice(options) if options else ""
            s = s[:m.start()] + chosen + s[m.end():]
        return s

    def _expand_mirrored_line(self, line: str, base_name: str, phase: str) -> str:
        pos = find_first_top_level_brace(line)
        if not pos:
            return self._expand_choices_recursively(line)
        start, end = pos
        inner = line[start+1:end]
        options = split_choices(inner)
        if not options:
            return self._expand_choices_recursively(line)
        # Deterministic anchor per (seed, file+line)
        idx = stable_pick_index(self.seed, f"{base_name}:{line}", len(options))
        if phase == "pos":
            # Positive gets only the chosen option
            core = options[idx]
        else:
            # Negative gets *all other* options (not the chosen one)
            others = [opt for i, opt in enumerate(options) if i != idx]
            # Join with commas so they appear as separate negatives
            core = ", ".join(others) if others else ""

        rebuilt = line[:start] + core + line[end+1:]
        return self._expand_choices_recursively(rebuilt)
