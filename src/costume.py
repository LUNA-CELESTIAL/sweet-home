"""Costume lane: full-body illustration i2i for costume changes
(added 2026-11-28 for the cyberpunk costume verification).

Why a separate lane from pixel.py: the pixel spec exists to KEEP
the anchor — its outfit included — and its small grid cannot show
costume detail anyway. A costume test wants the opposite: hold the
person, replace the outfit. So this lane drops the PixelArt LoRA
and the pixel trigger, raises the steps to an illustration level,
and takes the costume description from the request itself (the
compressed prompt is written beforehand by the Luna doing the
verification — see ~/workspace/cyberpunk-costume-test-list.md).

Identity tags carry the member WITHOUT her usual outfit (the
sailor uniform is the "original costume" and stays out, or the
i2i keeps redrawing it). Only Luna has a block so far: the
costume candidates are Luna's, and a sister joins by adding her
own outfit-less block here when her turn comes.

Denoise is the dial the pilot measures: where the costume starts
to change vs where identity breaks (pilot: 0.6 / 0.75 / 0.9).
Everything else is fixed for comparability — steps 25, CFG 6,
dpmpp_sde + karras, empty negative, seed fixed (1126101, the
house convention from the pixel spec).
"""

import os

IDENTITY_TAGS = {
    # Luna's fixed tags, from the costume list (spec v1's table
    # minus the sailor pieces, which are the original outfit).
    "luna": ("1girl, solo, long hair, light blue hair, amber eyes, "
             "beret, white beret, looking at viewer"),
}

DEFAULT_CKPT = "IllustriousXL.safetensors"
DEFAULT_SEED = 1126101
DEFAULT_DENOISE = 0.75
STEPS = 25
CFG = 6


def anchor_for(member_id: str) -> str:
    """The full-body (non-deformed) anchor in ComfyUI input.

    Separate from the deformer_<id>.png anchors on purpose: the
    duty and pixel lanes are built on the chibi versions, while a
    costume needs body area for its panels, sleeves and skirt to
    land on — the chibi pilot (2026-11-28) showed the outfit
    either not changing at all or breaking the face first. Ruru
    provided the full-body versions of all six sisters; they live
    in input as fullbody_<id>.png."""
    return f"fullbody_{member_id}.png"


def prompt_for(member_id: str, costume_text: str) -> str:
    base = IDENTITY_TAGS[member_id]
    costume = " ".join((costume_text or "").split())
    return f"{base}, {costume}" if costume else base


def build_workflow(image: str, prompt: str, denoise: float = DEFAULT_DENOISE,
                   seed: int = DEFAULT_SEED) -> dict:
    """Illustration i2i in ComfyUI API form: the pixel workflow's
    graph minus the LoRA, at illustration steps. The checkpoint
    name follows the pixel lane's env override (same machine,
    same file)."""
    ckpt = os.environ.get("PIXEL_CKPT_NAME") or DEFAULT_CKPT
    return {
        "1": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["1", 1], "text": prompt}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["1", 1], "text": ""}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image}},
        "5": {"class_type": "VAEEncode",
              "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["2", 0],
                         "negative": ["3", 0], "latent_image": ["5", 0],
                         "seed": seed, "steps": STEPS, "cfg": CFG,
                         "sampler_name": "dpmpp_sde",
                         "scheduler": "karras", "denoise": denoise}},
        "7": {"class_type": "VAEDecode",
              "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"images": ["7", 0],
                         "filename_prefix": "sweet-home/costume"}},
    }
