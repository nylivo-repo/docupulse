import logging
from app.core.config import settings
import os
import re
import shutil
from typing import Dict, Any, List, Tuple, Optional
import pypdfium2 as pdfium
import pdfplumber
from PIL import Image

IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"]
TEXT_EXTS = [".txt", ".md", ".json", ".csv"]

# Pages whose text layer holds fewer characters than this are treated as scanned and sent to OCR.
MIN_TEXT_CHARS = 20


def _clean_token(text: str) -> str:
    return re.sub(r"[^\w]", "", text.lower())


def _restore_spaces(text: str) -> str:
    """
    The bundled OCR model often drops spaces ("NorthwindTradersLtd", "ShipTo:Warehouse4,Pune").
    Re-insert them at lower-to-upper case changes, after a lowercase word followed by a digit,
    and after a colon or comma that runs into the next word.
    """
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Z]{2})(?=[A-Z][a-z]{2})", " ", text)
    text = re.sub(r"(?<=[a-z]{2})(?=\d)", " ", text)
    text = re.sub(r"(?<=[:,;])(?=[A-Za-z])", " ", text)
    text = re.sub(r"(?<=[A-Za-z]):(?=[\dA-Za-z$€£#+(])", ": ", text)
    return text


class LocalOCR:
    """
    Optional offline OCR. Uses RapidOCR (ONNX models bundled in the pip wheel) or the
    Tesseract binary when either is installed. Neither needs network access at runtime.
    """
    _engine = None
    _engine_name = None
    _checked = False

    @classmethod
    def engine_name(cls) -> Optional[str]:
        cls._load()
        return cls._engine_name

    @classmethod
    def _load(cls):
        if cls._checked:
            return
        cls._checked = True
        try:
            from rapidocr_onnxruntime import RapidOCR
            cls._engine = RapidOCR()
            cls._engine_name = "rapidocr"
            return
        except Exception:
            pass
        try:
            import pytesseract
            if shutil.which("tesseract"):
                cls._engine = pytesseract
                cls._engine_name = "tesseract"
        except Exception:
            pass

    @classmethod
    def ocr_image(cls, image: Image.Image) -> List[Dict[str, Any]]:
        """Returns words as {text, x0, y0, x1, y1} in pixel coordinates, in reading order."""
        cls._load()
        if not cls._engine:
            return []
        words = []
        if cls._engine_name == "rapidocr":
            import numpy as np
            result, _ = cls._engine(np.array(image.convert("RGB")))
            for box, text, _score in result or []:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                # RapidOCR returns text lines; split them into words with proportional boxes
                tokens = _restore_spaces(text).split()
                if not tokens:
                    continue
                x0, x1 = min(xs), max(xs)
                total = sum(len(t) for t in tokens) + len(tokens) - 1
                cursor = 0
                for t in tokens:
                    wx0 = x0 + (x1 - x0) * cursor / total
                    cursor += len(t)
                    wx1 = x0 + (x1 - x0) * cursor / total
                    cursor += 1
                    words.append({"text": t, "x0": wx0, "y0": min(ys), "x1": wx1, "y1": max(ys)})
        else:
            data = cls._engine.image_to_data(image, output_type=cls._engine.Output.DICT)
            for i, t in enumerate(data["text"]):
                if t and t.strip():
                    words.append({
                        "text": t.strip(),
                        "x0": data["left"][i], "y0": data["top"][i],
                        "x1": data["left"][i] + data["width"][i], "y1": data["top"][i] + data["height"][i],
                    })
        return words

    @staticmethod
    def words_to_text(words: List[Dict[str, Any]]) -> str:
        """Groups words into lines by vertical position."""
        lines: List[List[Dict[str, Any]]] = []
        for w in sorted(words, key=lambda w: (w["y0"], w["x0"])):
            h = max(1.0, w["y1"] - w["y0"])
            if lines and abs(lines[-1][0]["y0"] - w["y0"]) < h * 0.5:
                lines[-1].append(w)
            else:
                lines.append([w])
        return "\n".join(" ".join(x["text"] for x in sorted(line, key=lambda w: w["x0"])) for line in lines)


class OCRExtractor:
    @staticmethod
    def render_pdf_to_images(file_path: str, output_dir: str) -> List[str]:
        """Renders each page (or the uploaded image itself) to PNG for the review canvas."""
        os.makedirs(output_dir, exist_ok=True)
        ext = os.path.splitext(file_path)[1].lower()
        image_paths = []
        try:
            if ext in IMAGE_EXTS:
                img = Image.open(file_path)
                frames = min(getattr(img, "n_frames", 1), settings.MAX_PAGES)
                for idx in range(frames):
                    img.seek(idx)
                    img_path = os.path.join(output_dir, f"page_{idx + 1}.png")
                    img.convert("RGB").save(img_path, format="PNG")
                    image_paths.append(img_path)
            elif ext == ".pdf":
                pdf = pdfium.PdfDocument(file_path)
                for page_idx in range(min(len(pdf), settings.MAX_PAGES)):
                    image = pdf[page_idx].render(scale=2.0).to_pil()
                    img_path = os.path.join(output_dir, f"page_{page_idx + 1}.png")
                    image.save(img_path, format="PNG")
                    image_paths.append(img_path)
        except Exception as e:
            logging.getLogger("idp.extract").warning("Page rendering failed: %s", e)
        return image_paths

    @staticmethod
    def _ocr_page(image: Image.Image, page_num: int) -> Tuple[str, List[Dict[str, Any]]]:
        w, h = image.size
        words = LocalOCR.ocr_image(image)
        boxes = [{
            "text": x["text"], "page": page_num,
            "x0": round(x["x0"] / w * 100, 2), "y0": round(x["y0"] / h * 100, 2),
            "x1": round(x["x1"] / w * 100, 2), "y1": round(x["y1"] / h * 100, 2),
        } for x in words]
        return LocalOCR.words_to_text(words), boxes

    @staticmethod
    def extract_text_and_boxes(file_path: str) -> Tuple[str, List[Dict[str, Any]], int, Dict[str, Any]]:
        """
        Extracts raw text and word-level bounding boxes normalized to percentages (0-100).
        Uses the PDF text layer when present and local OCR for scanned pages and images.
        Returns (text, words, page_count, info) where info describes how the text was obtained.
        """
        ext = os.path.splitext(file_path)[1].lower()
        full_text = ""
        words_with_boxes: List[Dict[str, Any]] = []
        page_count = 1
        info: Dict[str, Any] = {"text_source": [], "ocr_engine": None, "warnings": []}

        if ext == ".pdf":
            try:
                with pdfplumber.open(file_path) as pdf:
                    page_count = len(pdf.pages)
                    if page_count > settings.MAX_PAGES:  # [storage] max_pages: bounds the work one upload can cause
                        info["warnings"].append(f"Only the first {settings.MAX_PAGES} of {page_count} pages were processed.")
                        page_count = settings.MAX_PAGES
                    for page_idx, page in enumerate(pdf.pages[:page_count]):
                        page_num = page_idx + 1
                        page_w = float(page.width) or 612.0
                        page_h = float(page.height) or 792.0
                        page_text = page.extract_text() or ""

                        if len(page_text.strip()) >= MIN_TEXT_CHARS:
                            info["text_source"].append("text_layer")
                            page_words = []
                            for w in page.extract_words() or []:
                                page_words.append({
                                    "text": w["text"], "page": page_num,
                                    "x0": round(float(w["x0"]) / page_w * 100, 2),
                                    "y0": round(float(w["top"]) / page_h * 100, 2),
                                    "x1": round(float(w["x1"]) / page_w * 100, 2),
                                    "y1": round(float(w["bottom"]) / page_h * 100, 2),
                                })
                        else:
                            image = page.to_image(resolution=200).original
                            page_text, page_words = OCRExtractor._ocr_page(image, page_num)
                            info["text_source"].append("ocr" if page_text else "none")
                        full_text += f"\n--- Page {page_num} ---\n" + page_text
                        words_with_boxes.extend(page_words)
            except Exception as e:
                info["warnings"].append(f"PDF could not be read: {e}")
        elif ext in IMAGE_EXTS:
            try:
                img = Image.open(file_path)
                page_count = min(getattr(img, "n_frames", 1), settings.MAX_PAGES)
                for idx in range(page_count):
                    img.seek(idx)
                    page_text, page_words = OCRExtractor._ocr_page(img.convert("RGB"), idx + 1)
                    info["text_source"].append("ocr" if page_text else "none")
                    full_text += f"\n--- Page {idx + 1} ---\n" + page_text
                    words_with_boxes.extend(page_words)
            except Exception as e:
                info["warnings"].append(f"Image could not be read: {e}")
        elif ext in TEXT_EXTS:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                full_text = f.read()
            info["text_source"].append("plain_text")
        else:
            info["warnings"].append(f"Unsupported file type '{ext}'.")

        if "none" in info["text_source"] or (ext in IMAGE_EXTS and not full_text.strip()):
            if LocalOCR.engine_name():
                info["warnings"].append("OCR found no readable text on one or more pages.")
            else:
                info["warnings"].append(
                    "Scanned page or image detected but no local OCR engine is installed "
                    "(install rapidocr-onnxruntime, or Tesseract + pytesseract). Fields need manual entry."
                )
        info["ocr_engine"] = LocalOCR.engine_name() if "ocr" in info["text_source"] else None
        return full_text, words_with_boxes, page_count, info

    @staticmethod
    def find_phrase_box(phrase: str, words_with_boxes: List[Dict[str, Any]], page: int = 1) -> Optional[Dict[str, Any]]:
        """Finds the bounding box covering the first exact occurrence of a phrase."""
        if not phrase or not words_with_boxes:
            return None
        tokens = [_clean_token(t) for t in str(phrase).split()]
        tokens = [t for t in tokens if t]
        if not tokens:
            return None

        cleaned = [_clean_token(w["text"]) for w in words_with_boxes]
        for i in range(len(words_with_boxes) - len(tokens) + 1):
            if all(cleaned[i + j] == t for j, t in enumerate(tokens)):
                matched = words_with_boxes[i: i + len(tokens)]
                if len({w["page"] for w in matched}) != 1:
                    continue
                return {
                    "page": matched[0]["page"],
                    "x0": min(w["x0"] for w in matched),
                    "y0": min(w["y0"] for w in matched),
                    "x1": max(w["x1"] for w in matched),
                    "y1": max(w["y1"] for w in matched),
                }

        # Tokens glued together in the PDF (e.g. "#INV-2026-8891"): match the joined phrase inside one word
        joined = "".join(tokens)
        if len(joined) >= 3:
            for w, c in zip(words_with_boxes, cleaned):
                if joined in c:
                    return {"page": w["page"], "x0": w["x0"], "y0": w["y0"], "x1": w["x1"], "y1": w["y1"]}
        return None
