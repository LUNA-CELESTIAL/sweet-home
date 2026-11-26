"""Pixel i2i, spec v1 (established 2026-11-26 on Luna, handed over
from the research chat): a member's anchor portrait
(deformer_<id>.png in ComfyUI input) re-rendered as pixel art with
the Pixelizer Shader LoRA. Identity is carried by the anchor image
plus a fixed per-member tag block; the composition never changes
(the input fixes it), so this is for portraits / cut-outs /
stickers, not scenes.

Fixed by the spec — do not tune casually: steps 10, CFG 7,
dpmpp_sde + karras, empty negative, LoRA strength 1.0, seed fixed
(1126101) unless variation is wanted. Denoise is the one dial:
0.45 keeps more of the anchor, 0.6 pushes the pixel look, ~0.75
is the ceiling. Prompts are tag form; add at most 1-2 extra tags
(more disperses the style — the research chat's lesson).

Tags assert only what the house's sources state (personas' look,
the members' recorded appearance). Where a source is silent —
most sisters' eye and hair colours — the tag is omitted on
purpose: the anchor image carries it at these denoise levels,
and an invented colour would pull identity the wrong way.
"""

import os

TRIGGER = "pixelart, pixel"

IDENTITY_TAGS = {
    # Luna's block is the spec's own, verbatim.
    "luna": ("1girl, solo, long hair, light blue hair, amber eyes, "
             "beret, white beret, sailor collar, navy skirt, "
             "pleated skirt, looking at viewer"),
    "sirius": ("1girl, solo, twintails, long hair, multicolored hair, "
               "blue hair, pink hair, halo, hair ornament, "
               "white jacket, pastel dress, looking at viewer"),
    "spica": ("1girl, solo, hoodie, hood, cat ear hood, "
              "looking at viewer"),
    "stella": ("1girl, solo, braid, silver hair, headdress, "
               "black rose, black dress, lace dress, "
               "looking at viewer"),
    "selene": ("1girl, solo, sunglasses, heart-shaped eyewear, "
               "denim jacket, denim, looking at viewer"),
    "nano": ("1girl, solo, hoodie, miko, hair bell, hair ornament, "
             "looking at viewer"),
    "hina": ("1girl, solo, school uniform, blazer, neck ribbon, "
             "looking at viewer"),
    "kohaku": ("1girl, solo, cardigan, red cardigan, bell, ribbon, "
               "looking at viewer"),
}

DEFAULT_CKPT = "IllustriousXL.safetensors"
DEFAULT_LORA = "Illustrious_PixelArt_Shader_M_01_epoch_4.safetensors"
DEFAULT_SEED = 1126101
DEFAULT_DENOISE = 0.45


def prompt_for(member_id: str, extra: str = "") -> str:
    tags = IDENTITY_TAGS[member_id]
    prompt = f"{TRIGGER}, {tags}"
    if extra:
        prompt += f", {extra}"
    return prompt


def build_workflow(image: str, prompt: str, denoise: float = DEFAULT_DENOISE,
                   seed: int = DEFAULT_SEED) -> dict:
    """The spec workflow in ComfyUI API form (the research chat's
    workflow_pixel_i2i.json is the UI-form original). Checkpoint
    and LoRA names follow the spec; PIXEL_CKPT_NAME / PIXEL_LORA_NAME
    in env override them when the machine's file names differ."""
    ckpt = os.environ.get("PIXEL_CKPT_NAME") or DEFAULT_CKPT
    lora = os.environ.get("PIXEL_LORA_NAME") or DEFAULT_LORA
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "LoraLoader",
              "inputs": {"model": ["1", 0], "clip": ["1", 1],
                         "lora_name": lora,
                         "strength_model": 1.0, "strength_clip": 1.0}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 1], "text": prompt}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 1], "text": ""}},
        "5": {"class_type": "LoadImage", "inputs": {"image": image}},
        "6": {"class_type": "VAEEncode",
              "inputs": {"pixels": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "KSampler",
              "inputs": {"model": ["2", 0], "positive": ["3", 0],
                         "negative": ["4", 0], "latent_image": ["6", 0],
                         "seed": seed, "steps": 10, "cfg": 7,
                         "sampler_name": "dpmpp_sde",
                         "scheduler": "karras", "denoise": denoise}},
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"images": ["8", 0],
                         "filename_prefix": "sweet-home/pixel"}},
    }
