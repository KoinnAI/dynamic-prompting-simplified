import os
import gradio as gr
from modules import scripts
from modules.processing import fix_seed
from dynprompt.expander import PromptExpander, WILDCARD_TOKEN_RE
from modules import script_callbacks

EXT_NAME = "Dynamic Prompt (Forge)"
EXT_VER = "1.4.1"  # Bumped version for clarity

# Default wildcards dir: <this_extension_root>/wildcards
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
        return EXT_NAME

    def show(self, is_img2img):
        # Show on both txt2img and img2img
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with gr.Accordion(f"{EXT_NAME} v{EXT_VER}", open=False):
            enable = gr.Checkbox(
                value=True,
                label="Enable dynamic prompt expansion",
            )
            wildcard_dir = gr.Textbox(
                value=DEFAULT_WILDCARD_DIR,
                label="Wildcard directory",
                info="Folder with *.txt wildcard lists (e.g., hats.txt → __hats__, hats-mir.txt → __hats-mir__).",
            )
            auto_mirror = gr.Checkbox(
                value=True,
                label="Automatically mirror -mir wildcards without explicitly adding them to the negative prompt",
                info="If a __name-mir__ appears (even nested) in the positive but not in negative, it will be auto-injected into the negative as the comma-separated 'other' options."
            )
            gr.Markdown(
                "Supports nested `{a|b|{c|d}}`, wildcards `__name__`, and mirrored wildcards `__name-mir__`.\n"
                "**Mirrored behavior:** positive gets the chosen option; negative gets all remaining options (comma-separated)."
            )
        # The order here must match process() arguments after `p`
        return [enable, wildcard_dir, auto_mirror]

    def process(self, p, enable, wildcard_dir, auto_mirror):
        # Banner so you can confirm this script loaded in the WebUI console
        print(f"[{EXT_NAME}] v{EXT_VER} loaded; enable={enable}, auto_mirror={auto_mirror}")

        if not enable:
            return

        if not wildcard_dir or not os.path.isdir(wildcard_dir):
            wildcard_dir = DEFAULT_WILDCARD_DIR

        # Ensure seeds are prepared; SD uses these to size prompt arrays
        fix_seed(p)
        base_seed = get_seed(p)

        try:
            total = max(1, p.batch_size * p.n_iter)
        except Exception:
            total = 1

        all_prompts = []
        all_negative = []

        # Raw user inputs (used both for expansion and token detection)
        pos_text_raw = p.prompt or ""
        neg_text_raw = p.negative_prompt or ""

        # Tokens typed by the user (top-level only)
        pos_tokens_raw = set(WILDCARD_TOKEN_RE.findall(pos_text_raw))
        neg_tokens_raw = set(WILDCARD_TOKEN_RE.findall(neg_text_raw))

        for i in range(total):
            seed_i = base_seed + i
            expander_pos = PromptExpander(wildcard_dir, seed=seed_i)
            expander_neg = PromptExpander(wildcard_dir, seed=seed_i)

            # Expand the user-provided texts
            pos_expanded = expander_pos.expand_prompt(pos_text_raw, phase="pos")
            neg_expanded = expander_neg.expand_prompt(neg_text_raw, phase="neg")

            # Optional convenience: auto-mirror -mir tokens from POS to NEG (including nested)
            if auto_mirror:
                # -mir tokens discovered during POS expansion (can come from nested wildcards)
                seen_mir_pos = set(expander_pos.seen_mir_tokens)
                # -mir tokens explicitly typed in POS box
                pos_mir_tokens_raw = {t for t in pos_tokens_raw if t.endswith("-mir")}

                # Inject any -mir tokens that appeared in POS but are not explicitly in NEG
                candidates = (seen_mir_pos | pos_mir_tokens_raw) - neg_tokens_raw
                if candidates:
                    auto_neg_src = ", ".join(f"__{t}__" for t in sorted(candidates))
                    auto_neg_expanded = expander_neg.expand_prompt(auto_neg_src, phase="neg").strip().strip(", ")
                    if auto_neg_expanded:
                        neg_expanded = (neg_expanded + ", " if neg_expanded else "") + auto_neg_expanded

            all_prompts.append(pos_expanded)
            all_negative.append(neg_expanded)

        # Provide expanded prompts to the pipeline and embed them in PNG metadata
        p.all_prompts = all_prompts
        p.all_negative_prompts = all_negative
        p.prompt = all_prompts[0]
        p.negative_prompt = all_negative[0]

        # Store expanded prompts in extra_generation_params for infotext
        p.extra_generation_params["Prompt"] = all_prompts[0]
        p.extra_generation_params["Negative prompt"] = all_negative[0]

        # Store raw prompts for reference but override p.prompt for UI transfer
        p.extra_generation_params["Raw prompt"] = pos_text_raw
        p.extra_generation_params["Raw negative prompt"] = neg_text_raw

    def after_component(self, component, **kwargs):
        """
        Hook into UI components to patch the 'Send to' button behavior.
        Ensure the expanded prompt is used when transferring to other tabs.
        """
        # Check if the component is a 'Send to' button
        if hasattr(component, "elem_id") and component.elem_id in [
            "txt2img_send_to_img2img",
            "txt2img_send_to_inpaint",
            "txt2img_send_to_extras",
            "img2img_send_to_img2img",
            "img2img_send_to_inpaint",
            "img2img_send_to_extras",
        ]:
            # Note: Directly modifying Gradio state here is complex and may require JavaScript injection
            # Instead, rely on p.prompt override and infotext for now
            print(f"[{EXT_NAME}] Detected 'Send to' button: {component.elem_id}")

# Register the callback to hook into UI components
script_callbacks.on_after_component(DynPromptScript().after_component)