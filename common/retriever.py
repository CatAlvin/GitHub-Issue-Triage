"""Local paragraph chunking and TF-IDF cosine retrieval."""
import math
import re
from collections import Counter


def tokenize(text: str):
    return re.findall(r"[a-z0-9]+", text.lower())


def fixed_size_chunks(text: str, size: int = 400, overlap: int = 80):
    """Chunk by character count with overlap. Simple, but can cut sentences."""
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks


def paragraph_chunks(text: str, max_size: int = 800):
    """Chunk on blank lines (semantic boundaries), merging small paragraphs."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) > max_size and buf:
            chunks.append(buf.strip())
            buf = ""
        buf += p + "\n\n"
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


class TfidfIndex:
    def __init__(self):
        self.docs = []          # [{"text":..., "meta":{...}}]
        self._df = Counter()
        self._vecs = []

    def add(self, text: str, **meta):
        self.docs.append({"text": text, "meta": meta})

    def build(self):
        self._df = Counter()
        tokenized = [set(tokenize(d["text"])) for d in self.docs]
        for toks in tokenized:
            self._df.update(toks)
        n = len(self.docs)
        self._vecs = []
        for d in self.docs:
            tf = Counter(tokenize(d["text"]))
            vec = {t: (1 + math.log(c)) * math.log(n / (1 + self._df[t]) + 1)
                   for t, c in tf.items()}
            self._vecs.append(vec)

    @staticmethod
    def _cosine(a: dict, b: dict) -> float:
        common = set(a) & set(b)
        num = sum(a[t] * b[t] for t in common)
        den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
        return num / den if den else 0.0

    def search(self, query: str, k: int = 3):
        n = max(len(self.docs), 1)
        tf = Counter(tokenize(query))
        qvec = {t: (1 + math.log(c)) * math.log(n / (1 + self._df.get(t, 0)) + 1)
                for t, c in tf.items()}
        scored = [(self._cosine(qvec, v), d) for v, d in zip(self._vecs, self.docs)]
        scored.sort(key=lambda x: -x[0])
        return [{"score": round(s, 4), **d} for s, d in scored[:k] if s > 0]
