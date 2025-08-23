# SD WebUI Dynamic Prompt Extension

This extension adds **dynamic prompting** to SD WebUI Forge, supporting advanced prompt features including nested choices, wildcard files, and mirrored wildcards.

## ✨ Features

- **Nested choices** with `{option1|option2|{nested1|nested2}}`
- **Wildcard expansion** with `__name__` → expands from `wildcards/name.txt`
- **Line-separated wildcard files** that may themselves contain braces and wildcards
- **Mirrored wildcards** with `__name-mir__`:
  - Positive prompt gets the **chosen option**
  - Negative prompt gets **all the other options, comma-separated**
  - Strict resolution: `__name-mir__` reads **only** `wildcards/name-mir.txt` (no fallback to `name.txt`)
- **Deterministic behavior** using the current generation seed
- Works for both **positive** and **negative** prompts
- Expanded prompts are saved into PNG metadata

## 📂 Installation

1. Navigate to your SD WebUI Forge installation directory.
2. Place this folder in `extensions/`:
   ```
   extensions/
     sd-webui-dynprompt/
       scripts/
         dynprompt.py
       dynprompt/
         __init__.py
         expander.py
       wildcards/
   ```
3. Restart SD WebUI Forge.

## 📑 Wildcard Files

- Located in the `wildcards/` directory (configurable).
- Each line is one possible expansion.
- Lines may contain further braces `{}` and wildcard calls.

**Example: `wildcards/hats.txt`**
```
{red hat|blue hat|{green hat|yellow hat|{black hat|gold hat}}}
beret
top hat
```

## 🔄 Mirrored Wildcards

- File name: `name-mir.txt` (called via `__name-mir__`).
- Ensures complementary picks between positive/negative prompts.

**Example: `wildcards/hats-mir.txt`**
```
{red hat|blue hat|green hat}
{tall hat|short hat|medium hat}
```

- Positive prompt: `portrait, __hats-mir__`
- Negative prompt: `lowres, __hats-mir__`
  - If pos → `red hat`, neg → `blue hat, green hat`
  - If pos → `short hat`, neg → `tall hat, medium hat`

This ensures that the **negative prompt excludes the token chosen in the positive prompt.**

### 🧩 Nested `-mir` behavior (auto-discovery)

Mirrored tokens can be **nested inside other wildcards**. If a wildcard you use in the **positive** prompt expands to another token like `__foo-mir__`, the extension can **automatically inject the mirrored complement** into the **negative** prompt (so you don’t have to add `__foo-mir__` manually).

- This requires the checkbox in the UI:  
  **“Automatically mirror -mir wildcards without explicitly adding them to the negative prompt.”** (enabled by default)
- The auto-inject only happens if the negative prompt does **not** already contain that `__*-mir__` token.
- Resolution is strict: `__foo-mir__` reads `wildcards/foo-mir.txt` only.

**Example (nested):**
```
wildcards/outfits.txt
---------------------
__hats-mir__, {casual|formal}

wildcards/hats-mir.txt
----------------------
{red hat|blue hat|green hat}
```

Usage:
- Positive: `portrait, __outfits__`
- Negative: *(leave blank or put your usual negatives)*

Behavior:
- The positive prompt expands `__outfits__` → which contains `__hats-mir__`.
- With the checkbox enabled, the extension auto-injects `__hats-mir__` into the **negative** and expands it there as the comma‑separated “other” options.
- If the seed picks **`red hat`** for positive, the negative gets **`blue hat, green hat`** automatically.

## ⚙️ Usage

- Write prompts as usual with `{}` and `__wildcards__`.
- Wildcards are recursively expanded.
- Mirrored wildcards respect complement logic.

**Prompt Example:**
```
Positive: portrait, {cinematic|studio|outdoor}, __hats__, soft lighting
Negative: lowres, bad anatomy, __hats-mir__
```

### UI Options
- **Enable dynamic prompt expansion** — master toggle.
- **Wildcard directory** — where your `.txt` wildcard files live.
- **Automatically mirror -mir wildcards without explicitly adding them to the negative prompt** —
  When on, any `__*-mir__` discovered in the **positive** (even nested within another wildcard) is appended to the **negative** prompt and expanded as the “others.”

## ✅ Notes

- Missing wildcard files resolve to empty string.
- Braces expand until fully resolved.
- Safety caps prevent runaway expansion.
- Deterministic per seed: line selection for wildcards is stable across runs; within a mirrored brace, the chosen index is mirrored so the negative sees the remaining options.

## Licence & Contributing

**Contributing**
- 1 fork this repository  
- 2 make changes  
- 3 submit pull request

**License:** GNU General Public License (GPLv3) (https://www.gnu.org/licenses/gpl-3.0.en.html)

Made for [Stable Diffusion WebUI Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge) <br>
Check out the version for [ComfyUI](https://github.com/RegulusAlpha/ComfyUI-DynPromptSimplified)
