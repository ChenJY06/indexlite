import unicodedata

from .tokenizer import tokenize


def excerpt(text: str, terms: list[str], width: int = 180) -> str:
    """Select a window near a dense group of query occurrences, preferring earlier ties."""
    wanted = set(terms)
    positions = []
    start = None
    # Original offsets survive Unicode normalization expanding or shrinking tokens.
    for i in range(len(text) + 1):
        is_word = i < len(text) and (
            text[i].isalnum() or unicodedata.category(text[i]).startswith("M")
        )
        if is_word and start is None:
            start = i
        elif not is_word and start is not None:
            if wanted.intersection(tokenize(text[start:i])):
                positions.append(start)
            start = None
    best_start, best_count, right = 0, -1, 0
    for left, position in enumerate(positions):
        window_start = max(0, position - width // 4)
        while right < len(positions) and positions[right] < window_start + width:
            right += 1
        if right - left > best_count:
            best_start, best_count = window_start, right - left
    end = min(len(text), best_start + width)
    body = " ".join(text[best_start:end].split())
    return ("…" if best_start else "") + body + ("…" if end < len(text) else "")
