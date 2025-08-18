
import os
import gradio as gr
from modules import scripts, shared
from modules.shared import opts
from dynprompt.expander import PromptExpander

EXT_NAME = "sd-webui-dynprompt"
DEFAULT_WILDCARD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wildcards")

def get_seed_from_p(p):
    try:
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
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with gr.Accordion("Dynamic Prompt", open=False):
            enable = gr.Checkbox(value=True, label="Enable dynamic prompt expansion")
            wildcard_dir = gr.Textbox(
                value=DEFAULT_WILDCARD_DIR,
                label="Wildcard directory",
                info="Folder with *.txt wildcard lists (e.g., hats.txt → __hats__)."
            )
            gr.Markdown(
                "Nested `{a|b|{c|d}}`, wildcards `__name__`, mirrored wildcards `__name-mir__`.\n"
                "Mirrored: positive picks one, negative gets all remaining (comma-separated)."
            )
        return [enable, wildcard_dir]

    # Use process() rather than before_process() for Forge reliability
    def process(self, p, enable, wildcard_dir):
        if not enable:
            return
        if not wildcard_dir or not os.path.isdir(wildcard_dir):
            wildcard_dir = DEFAULT_WILDCARD_DIR

        seed = get_seed_from_p(p)
        expander = PromptExpander(wildcard_dir, seed=seed)

        try:
            p.prompt = expander.expand_prompt(p.prompt or "", phase="pos")
        except Exception as e:
            print(f"[{EXT_NAME}] Error expanding positive prompt: {e}")

        try:
            p.negative_prompt = expander.expand_prompt(p.negative_prompt or "", phase="neg")
        except Exception as e:
            print(f"[{EXT_NAME}] Error expanding negative prompt: {e}")

# Optional: global setting for default dir
def on_ui_settings():
    section = ("dynamic_prompt", "Dynamic Prompt")
    shared.opts.add_option(
        "dynprompt_wildcard_dir",
        shared.OptionInfo(DEFAULT_WILDCARD_DIR, "Default wildcard directory", section=section)
    )

try:
    from modules import script_callbacks
    script_callbacks.on_ui_settings(on_ui_settings)
except Exception:
    pass
