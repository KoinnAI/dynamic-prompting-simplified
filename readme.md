# SD WebUI Dynamic Prompt Extension

This extension adds **dynamic prompting** to SD WebUI Forge, supporting advanced prompt features including nested choices, wildcard files, and mirrored wildcards.

## ✨ Features

- **Nested choices** with `{option1|option2|{nested1|nested2}}`
- **Wildcard expansion** with `__name__` → expands from `wildcards/name.txt`
- **Line-separated wildcard files** that may themselves contain braces and wildcards
- **Mirrored wildcards** with `__name-mir__`:
  - Positive prompt gets the **chosen option**
  - Negative prompt gets **all the other options, comma-separated**
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

- File name: `name-mir.txt` (called via `__name-mir__`)
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

## ⚙️ Usage

- Write prompts as usual with `{}` and `__wildcards__`.
- Wildcards are recursively expanded.
- Mirrored wildcards respect complement logic.

**Prompt Example:**
```
Positive: portrait, {cinematic|studio|outdoor}, __hats__, soft lighting
Negative: lowres, bad anatomy, __hats-mir__
```

## 🛠️ Settings

- Enable/disable dynamic prompting in the UI under **Dynamic Prompt** accordion.
- Configure the default `wildcards/` directory in settings.

## ✅ Notes

- Missing wildcard files resolve to empty string.
- Braces expand until fully resolved.
- Safety caps prevent runaway expansion.

---

Made with ❤️ for prompt tinkerers.