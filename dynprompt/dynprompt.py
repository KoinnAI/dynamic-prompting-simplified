import os
from modules import scripts, script_callbacks, shared
from modules.shared import opts
import gradio as gr

from dynprompt.expander import PromptExpander

EXT_NAME = "sd-webui-dynprompt"
DEFAULT_WILDCARD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wildcards")

def get_seed_from_p(p):
    # Try to derive a stable seed for deterministic mirrored choices
    try:
        # txt2img: p.seed is an int or -1; if -1 use p.all_seeds[0] later
        seed = p.seed
        if seed is None or seed == -1:
            if getattr(p, "all_seeds", None):
                seed = p.all_seeds[0]
        if seed is None or seed == -1:
            seed = 0
        return int(seed)
    except Exception:
        return 0

class DynPromptScript(scripts.Script):
    def title(self):
        return "Dynamic Prompt (Forge)"

    def show(self, is_img2img):
        # Show on both tabs
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with gr.Accordion("Dynamic Prompt", open=False):
            enable = gr.Checkbox(value=True, label="Enable dynamic prompt expansion")
            wildcard_dir = gr.Textbox(
                value=DEFAULT_WILDCARD_DIR,
                label="Wildcard directory",
                info="Folder containing *.txt wildcard lists (e.g., hats.txt → __hats__)."
            )
            note = gr.Markdown(
                "Supports nested `{a|b|{c|d}}`, wildcard tokens like `__name__`, and mirrored wildcards `__name-mir__`.\n"
                "**Tip:** Wildcard files may contain braces and other wildcards."
            )
        return [enable, wildcard_dir]

    def before_process(self, p, enable, wildcard_dir):
        if not enable:
            return

        if not wildcard_dir or not os.path.isdir(wildcard_dir):
            wildcard_dir = DEFAULT_WILDCARD_DIR

        seed = get_seed_from_p(p)

        # Expand positive and negative separately with the same RNG seed,
        # but different 'phase' so -mir picks invert correctly.
        expander_pos = PromptExpander(wildcard_dir, seed=seed)
        expander_neg = PromptExpander(wildcard_dir, seed=seed)

        try:
            p.prompt = expander_pos.expand_prompt(p.prompt or "", phase="pos")
        except Exception as e:
            print(f"[{EXT_NAME}] Error expanding positive prompt: {e}")

        try:
            p.negative_prompt = expander_neg.expand_prompt(p.negative_prompt or "", phase="neg")
        except Exception as e:
            print(f"[{EXT_NAME}] Error expanding negative prompt: {e}")

# (Optional) add a setting to make the wildcard dir globally configurable
def on_ui_settings():
    section = ("dynamic_prompt", "Dynamic Prompt")
    shared.opts.add_option(
        "dynprompt_wildcard_dir",
        shared.OptionInfo(DEFAULT_WILDCARD_DIR, "Default wildcard directory", section=section)
    )

script_callbacks.on_ui_settings(on_ui_settings)
