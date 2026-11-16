"""Validate and shrink uploaded photos before they are sent to the AI."""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024   # 10 MB raw upload
MAX_SIDE_PX = 1280                    # plenty for object recognition, keeps latency low


class InvalidImage(ValueError):
    pass


def prepare_image(uploaded_file) -> bytes:
    """Return JPEG bytes (EXIF-rotated, max 1280px) or raise InvalidImage."""
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise InvalidImage("That photo is too large (max 10 MB). Try a smaller one.")
    try:
        img = Image.open(uploaded_file)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise InvalidImage("That file doesn't look like a valid image.")
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()
