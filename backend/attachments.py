"""
Attachment files on disk: storing an upload, deciding its kind, and its preview.

Each file is saved under Settings.attachments_dir with a random stored_name, never
the uploaded filename, which is kept only for display and downloads. Images get a
small JPEG preview in attachments_dir/previews/. Archiving an attachment leaves
both on disk.
"""

import codecs
import mimetypes
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps

from GoldrynModels import clean_filename

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
# Slack for multipart boundaries and part headers when checking Content-Length.
MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_FILENAME_CHARS = 255

PREVIEW_SIZE = 800  # longest side, in pixels
# Formats every desktop browser can show in a tab. Pillow reads more (TIFF, PSD...),
# but those couldn't open in a tab, so they're plain downloads with no preview.
BROWSER_IMAGE_FORMATS = {"JPEG", "PNG", "GIF", "WEBP", "BMP"}
# How much of a file is read to tell a PDF or a text file from anything else.
SNIFF_BYTES = 8192


@dataclass(frozen=True)
class StoredFile:
    stored_name: str
    kind: str  # 'image' | 'pdf' | 'text' | 'file', see db.MIGRATIONS[1]
    content_type: str
    size_bytes: int


def file_path(root: Path, stored_name: str) -> Path:
    return root / stored_name


def preview_path(root: Path, stored_name: str) -> Path:
    return root / "previews" / f"{stored_name}.jpg"


def ensure_dirs(root: Path) -> None:
    (root / "previews").mkdir(parents=True, exist_ok=True)


def store_upload(root: Path, source: BinaryIO, filename: str) -> StoredFile:
    """Copy an upload to disk and classify it. Nothing is left behind if this raises."""
    stored_name = uuid.uuid4().hex
    path = file_path(root, stored_name)
    source.seek(0)
    try:
        with open(path, "wb") as out:
            shutil.copyfileobj(source, out, 1024 * 1024)
        kind, content_type = _classify(path, preview_path(root, stored_name), filename)
        return StoredFile(stored_name, kind, content_type, path.stat().st_size)
    except BaseException:
        delete_files(root, stored_name)
        raise


def delete_files(root: Path, stored_name: str) -> None:
    """For an upload whose row never made it into the DB. Archived attachments keep their files."""
    file_path(root, stored_name).unlink(missing_ok=True)
    preview_path(root, stored_name).unlink(missing_ok=True)


def upload_filename(raw: str) -> str:
    """The display name for an upload: cleaned like a rename, cut to length, and never empty."""
    return clean_filename(raw)[:MAX_FILENAME_CHARS].strip() or "file"


def unique_filename(name: str, taken: set[str]) -> str:
    """`name`, or `name (2).ext`, `name (3).ext`... if the item already has a file by that name."""
    if name not in taken:
        return name
    suffix = Path(name).suffix
    stem = name[: len(name) - len(suffix)]
    n = 2
    while True:
        tag = f" ({n})"
        candidate = stem[: MAX_FILENAME_CHARS - len(tag) - len(suffix)] + tag + suffix
        if candidate not in taken:
            return candidate
        n += 1


# ============================================================================
# Classification
#
# Decided from the bytes, not the filename or the browser's Content-Type, so a
# renamed .html can't pass as an image or PDF. Only 'image', 'pdf' and 'text'
# are ever shown in a tab; 'file' is always a download.
# ============================================================================


def _classify(path: Path, preview: Path, filename: str) -> tuple[str, str]:
    image_type = _write_preview(path, preview)
    if image_type:
        return "image", image_type

    with open(path, "rb") as f:
        head = f.read(SNIFF_BYTES)
    if head.startswith(b"%PDF-"):
        return "pdf", "application/pdf"

    guessed = mimetypes.guess_type(filename)[0]
    if guessed and guessed.startswith("text/") and _looks_like_utf8_text(head):
        return "text", guessed
    return "file", guessed or "application/octet-stream"


def _looks_like_utf8_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    try:
        # Incremental, so a multi-byte character cut off at SNIFF_BYTES isn't an error.
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError:
        return False
    return True


def _write_preview(source: Path, target: Path) -> str | None:
    """Write a JPEG preview if Pillow can decode `source` as a browser image. Returns its MIME type."""
    try:
        with Image.open(source) as img:
            if img.format not in BROWSER_IMAGE_FORMATS:
                return None
            content_type = Image.MIME[img.format]
            img.draft("RGB", (PREVIEW_SIZE * 2, PREVIEW_SIZE * 2))  # fast JPEG downscale while decoding
            # Phone photos are often stored sideways with an EXIF rotation flag.
            preview = ImageOps.exif_transpose(img)
            preview.thumbnail((PREVIEW_SIZE, PREVIEW_SIZE))
            if preview.mode in ("RGBA", "LA", "P", "PA"):
                # JPEG has no transparency: flatten onto white, not black.
                rgba = preview.convert("RGBA")
                preview = Image.new("RGB", rgba.size, "white")
                preview.paste(rgba, mask=rgba.getchannel("A"))
            else:
                preview = preview.convert("RGB")
            preview.save(target, "JPEG", quality=80)
        return content_type
    except Exception:  # not an image, truncated, or a decompression bomb
        target.unlink(missing_ok=True)
        return None
