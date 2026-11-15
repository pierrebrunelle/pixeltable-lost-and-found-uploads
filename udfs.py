"""UDFs for the lost-and-found upload API (pure Python, no table imports)."""

from __future__ import annotations

import PIL.Image

import pixeltable as pxt

CAPTION_MODEL = 'gpt-4o-mini'
CLIP_MODEL = 'openai/clip-vit-base-patch32'

CAPTION_PROMPT = (
    'This photo was uploaded by a neighbor who found an item. In one sentence of at most 20 words, '
    'name the item and its color, material, brand or any distinguishing marks. No preamble.'
)

# coarse color names for a cheap, model-free hint next to the caption
_PALETTE = {
    'black': (25, 25, 25),
    'white': (235, 235, 235),
    'gray': (128, 128, 128),
    'red': (190, 40, 40),
    'orange': (230, 130, 40),
    'yellow': (225, 210, 60),
    'green': (60, 150, 70),
    'blue': (50, 90, 190),
    'purple': (120, 60, 150),
    'brown': (120, 80, 45),
    'pink': (230, 150, 170),
}


@pxt.udf
def color_hint(img: PIL.Image.Image) -> str:
    """Name of the palette color closest to the image's most common color (after quantizing to 4 colors)."""
    small = img.convert('RGB').resize((64, 64))
    q = small.quantize(colors=4)
    palette = q.getpalette() or []
    counts = sorted(q.getcolors() or [], reverse=True)
    if not counts:
        return 'unknown'
    idx = counts[0][1]
    rgb = tuple(palette[idx * 3 : idx * 3 + 3])
    return min(_PALETTE, key=lambda name: sum((a - b) ** 2 for a, b in zip(_PALETTE[name], rgb)))


@pxt.udf
def vision_messages(prompt: str, img: PIL.Image.Image) -> list[dict]:
    """Chat messages that send the (already downsized) photo to a vision model at low detail."""
    import base64
    import io

    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='JPEG', quality=80)
    url = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
    return [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': url, 'detail': 'low'}},
            ],
        }
    ]


@pxt.udf
def shortlist(hits: list[dict] | None) -> list[dict]:
    """Compact match list for a lost report: item id, where it was found, caption and a rounded score."""
    out = []
    for h in hits or []:
        out.append(
            {
                'item_id': str(h.get('item_id')),
                'spot': h.get('spot'),
                'caption': h.get('caption'),
                'score': round(float(h.get('score') or 0.0), 3),
            }
        )
    return out
