"""Files and pictures the user attaches to a message.

The web page sends each one as {name, type, data} with base64 data. We sort
them into pictures, PDFs and text files so each goes to Claude the right way.
"""

import base64
import io

from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024

IMAGE_EXTS = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
              "gif": "image/gif", "webp": "image/webp"}


class Attachment:
    def __init__(self, name: str, kind: str, mime: str, data: bytes, text: str = ""):
        self.name = name
        self.kind = kind  # "image", "pdf" or "text"
        self.mime = mime
        self.data = data
        self.text = text

    @property
    def b64(self) -> str:
        return base64.b64encode(self.data).decode()


def parse(raw: dict) -> Attachment:
    """Turn one {name, type, data} upload into an Attachment, or raise ValueError."""
    name = raw.get("name") or "file"
    mime = (raw.get("type") or "").lower()
    try:
        data = base64.b64decode(raw.get("data") or "", validate=True)
    except ValueError:
        raise ValueError(f"'{name}' didn't upload correctly. Try again.")
    if len(data) > MAX_BYTES:
        raise ValueError(f"'{name}' is too big (max 10 MB).")

    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in IMAGE_EXTS or mime in IMAGE_EXTS.values():
        return Attachment(name, "image", IMAGE_EXTS.get(ext, mime), data)
    if ext == "pdf" or mime == "application/pdf":
        try:
            pages = PdfReader(io.BytesIO(data)).pages
            text = "\n\n".join(page.extract_text() or "" for page in pages).strip()
        except Exception:
            raise ValueError(f"Couldn't open the PDF '{name}'.")
        return Attachment(name, "pdf", "application/pdf", data, text or "(no readable text in this PDF)")
    try:
        return Attachment(name, "text", "text/plain", data, data.decode("utf-8"))
    except UnicodeDecodeError:
        raise ValueError(f"Can't read '{name}'. Use a text, PDF or picture (PNG, JPG, GIF, WebP) file.")


def default_question(attachments) -> str:
    """What to ask when the user sends attachments with no message."""
    if any(a.kind == "image" for a in attachments):
        return "Describe this picture."
    return "Summarize the attached file."
