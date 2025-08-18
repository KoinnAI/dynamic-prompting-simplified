
import os
import gradio as gr
from modules import scripts
from modules.processing import fix_seed
from dynprompt.expander import PromptExpander

EXT_NAME = "sd-webui-dynprompt"
DEFAULT_WILDCARD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wildcards")

def get_seed(p):
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
            wildcard_dir = gr.Textbox(value=DEFAULT_WILDCARD_DIR, label="Wildcard directory")
            gr.Markdown("Mirrored wildcards: positive picks one, negative gets all remaining (comma-separated).")
        return [enable, wildcard_dir]

    def process(self, p, enable, wildcard_dir):
        if not enable:
            return
        if not wildcard_dir or not os.path.isdir(wildcard_dir):
            wildcard_dir = DEFAULT_WILDCARD_DIR

        # Ensure seeds are prepared so we know the intended image count
        fix_seed(p)

        # Determine how many prompts SD will render
        try:
            num_images = p.batch_size * p.n_iter
            if hasattr(p, "hr_second_pass_steps") and getattr(p, "enable_hr", False):
                # still the same prompt count; note: HR prompts may differ, but we only expand base prompts
                pass
        except Exception:
            num_images = 1

        base_seed = get_seed(p)

        all_prompts = []
        all_neg_prompts = []

        # Expand per image deterministically (seed + index) so each image can vary
        for i in range(max(1, num_images)):
            seed_i = base_seed + i
            expander_pos = PromptExpander(wildcard_dir, seed=seed_i)
            expander_neg = PromptExpander(wildcard_dir, seed=seed_i)

            pos_text = (p.prompt or "")
            neg_text = (p.negative_prompt or "")

            pos_expanded = expander_pos.expand_prompt(pos_text, phase="pos")
            neg_expanded = expander_neg.expand_prompt(neg_text, phase="neg")

            all_prompts.append(pos_expanded)
            all_neg_prompts.append(neg_expanded)

        # Populate arrays so Forge/A1111 uses expanded prompts AND saves them to PNG metadata
        p.all_prompts = all_prompts
        p.all_negative_prompts = all_neg_prompts

        # Set the "current" prompt fields too (first item)
        p.prompt = all_prompts[0]
        p.negative_prompt = all_neg_prompts[0]
