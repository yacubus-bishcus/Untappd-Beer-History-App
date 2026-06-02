import re
from typing import Optional


def _rating_float(value: str) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"(?<!\d)([0-5](?:\.\d{1,2})?)(?!\d)", str(value))
    if not match:
        return None
    try:
        rating = float(match.group(1))
    except ValueError:
        return None
    return rating if 0.0 <= rating <= 5.0 else None


def _extract_labeled_rating_from_text(text: str, label: str) -> Optional[float]:
    if not text:
        return None
    label_pattern = r"\s*".join(re.escape(part) for part in label.split())
    patterns = [
        rf"{label_pattern}\s*(?:rating)?\s*[:\-(]*\s*([0-5](?:\.\d{{1,2}})?)",
        rf"{label_pattern}.{{0,80}}?([0-5](?:\.\d{{1,2}})?)",
        rf"([0-5](?:\.\d{{1,2}})?).{{0,30}}?{label_pattern}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.S)
        if match:
            rating = _rating_float(match.group(1))
            if rating is not None:
                return rating
    return None


def _attribute_texts(item) -> list[str]:
    values = []
    attrs_to_check = ("title", "aria-label", "data-title", "data-original-title", "alt")
    for node in item.find_all(True):
        for attr in attrs_to_check:
            value = node.get(attr)
            if value:
                values.append(str(value))
    return values


def _extract_labeled_rating(item, label: str) -> Optional[float]:
    texts = []
    full_text = " ".join(item.stripped_strings)
    if full_text:
        texts.append(full_text)
    texts.extend(_attribute_texts(item))

    for text in texts:
        rating = _extract_labeled_rating_from_text(text, label)
        if rating is not None:
            return rating

    pieces = [piece.strip() for piece in item.stripped_strings if piece and piece.strip()]
    for index, piece in enumerate(pieces):
        if label.lower() not in piece.lower():
            continue
        rating = _rating_float(piece)
        if rating is not None:
            return rating
        for offset in range(1, 4):
            if index + offset >= len(pieces):
                break
            rating = _rating_float(pieces[index + offset])
            if rating is not None:
                return rating

    # Some Untappd fragments put the numeric value immediately before the label.
    for index, piece in enumerate(pieces):
        if label.lower() not in piece.lower() or index == 0:
            continue
        for offset in range(1, 3):
            if index - offset < 0:
                break
            rating = _rating_float(pieces[index - offset])
            if rating is not None:
                return rating
    return None


def patch_untappd_selenium_rating_parser():
    """Patch untapped_selenium.parse_beer_item with more defensive rating extraction."""
    import untapped_selenium

    original_parse = untapped_selenium.parse_beer_item
    if getattr(original_parse, "_rating_parser_patched", False):
        return

    def parse_beer_item_with_robust_ratings(item):
        parsed = original_parse(item)
        if not parsed:
            return parsed

        if parsed.get("your_rating") is None:
            parsed["your_rating"] = _extract_labeled_rating(item, "your rating")
        if parsed.get("global_rating") is None:
            parsed["global_rating"] = _extract_labeled_rating(item, "global rating")

        return parsed

    parse_beer_item_with_robust_ratings._rating_parser_patched = True
    untapped_selenium.parse_beer_item = parse_beer_item_with_robust_ratings
