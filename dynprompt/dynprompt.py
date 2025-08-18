import os
import gradio as gr
from modules import scripts
from modules.processing import fix_seed
from dynprompt.expander import PromptExpander, WILDCARD_TOKEN_RE

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
            wildcard_dir = gr.Textbox(
                value=DEFAULT_WILDCARD_DIR,
                label="Wildcard directory",
                info="Folder with *.txt wildcard lists (e.g., hats.txt → __hats__)."
            )
            auto_mirror = gr.Checkbox(
                value=True,
                label="Automatically mirror -mir wildcards without explicitly adding them to the negative prompt"
            )
            gr.Markdown(
                "Supports nested `{a|b|{c|d}}`, wildcards `__name__`, and mirrored wildcards `__name-mir__`.\n"
                "Mirrored: **positive** gets the chosen option; **negative** gets all remaining options (comma-separated)."
            )
        # IMPORTANT: return components in the same order that process() expects
        return [enable, wildcard_dir, auto_mirror]

    def process(self, p, enable, wildcard_dir, auto_mirror):
        if not enable:
            return

        if not wildcard_dir or not os.path.isdir(wildcard_dir):
            wildcard_dir = DEFAULT_WILDCARD_DIR

        # Ensure seeds are prepared; SD uses these for array prompts/metadata
        fix_seed(p)
        base_seed = get_seed(p)

        try:
            total = max(1, p.batch_size * p.n_iter)
        except Exception:
            total = 1

        all_prompts = []
        all_neg = []

        # Raw user inputs (used to detect which -mir tokens were explicitly placed)
        pos_text_raw = p.prompt or ""
        neg_text_raw = p.negative_prompt or ""

        # Pre-extract raw tokens once (for auto mirror logic)
        pos_tokens_raw = set(WILDCARD_TOKEN_RE.findall(pos_text_raw))
        neg_tokens_raw = set(WILDCARD_TOKEN_RE.findall(neg_text_raw))

        for i in range(total):
            seed_i = base_seed + i
            expander_pos = PromptExpander(wildcard_dir, seed=seed_i)
            expander_neg = PromptExpander(wildcard_dir, seed=seed_i)

            # Expand the user-provided texts
            pos_expanded = expander_pos.expand_prompt(pos_text_raw, phase="pos")
            neg_expanded = expander_neg.expand_prompt(neg_text_raw, phase="neg")

            # --- Auto-mirror injection (optional) ---
            if auto_mirror:
                # Find -mir tokens present in POS raw text but not explicitly present in NEG raw text
                pos_mir_tokens = [t for t in pos_tokens_raw if t.endswith("-mir")]
                inject_tokens = [t for t in pos_mir_tokens if t not in neg_tokens_raw]

                if inject_tokens:
                    # Build a synthetic negative snippet composed of those tokens,
                    # then expand with phase="neg" so it becomes the "others" list.
                    auto_neg_src = ", ".join(f"__{t}__" for t in inject_tokens)
                    auto_neg_expanded = expander_neg.expand_prompt(auto_neg_src, phase="neg").strip().strip(", ")

                    if auto_neg_expanded:
                        neg_expanded = (neg_expanded + ", " if neg_expanded else "") + auto_neg_expanded

            all_prompts.append(pos_expanded)
            all_neg.append(neg_expanded)

        # Populate arrays so Forge uses expanded prompts and writes them into PNG metadata
        p.all_prompts = all_prompts
        p.all_negative_prompts = all_neg

        # Keep the first for UI preview
        p.prompt = all_prompts[0]
        p.negative_prompt = all_neg[0]
