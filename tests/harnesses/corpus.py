"""Read-only corpus observation harness.

Everything here is designed so a private corpus can be *characterized without being copied*:
the content fingerprint holds only relative paths, entry kinds, sizes, and SHA-256 digests;
the multiset comparison holds only digests; and failures carry reason codes, never a path,
filename, value, or the underlying exception text (which could embed a private filename).
"""

from __future__ import annotations

import collections
import contextlib
import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path


class UnsafeCorpusEntry(Exception):
    """A symlink or other non-regular filesystem entry was found under the corpus root."""


class UnreadableCorpusEntry(Exception):
    """A corpus entry could not be read; carries a reason code only (never a path/value)."""


@contextlib.contextmanager
def _redact_read_failures() -> Iterator[None]:
    """Translate any read/parse failure into a reason-coded ``UnreadableCorpusEntry``.

    The underlying exceptions (``PermissionError``/``OSError``/``json.JSONDecodeError``, plus
    the arbitrary types PyMuPDF raises for malformed PDFs) embed a real absolute path,
    filename, or payload snippet in their ``str()``. Catching them here — and re-raising with
    ``from None`` so the original traceback frame is dropped — keeps that text out of every
    assertion and CI log. ``permission-denied`` is distinguished; everything else collapses
    to ``read-error``. ``BaseException`` (``KeyboardInterrupt``/``SystemExit``) is not caught.
    """
    try:
        yield
    except (UnsafeCorpusEntry, UnreadableCorpusEntry):
        raise  # already reason-coded; do not reclassify
    except PermissionError:
        raise UnreadableCorpusEntry("permission-denied") from None
    except Exception:
        raise UnreadableCorpusEntry("read-error") from None


@dataclass(frozen=True, slots=True, order=True)
class CorpusEntry:
    relative_path: str
    kind: str  # "file" or "dir"
    size: int
    digest: str  # sha256 hex of file bytes; "" for directories


@dataclass(frozen=True, slots=True)
class CorpusFingerprint:
    entries: tuple[CorpusEntry, ...]

    def digest(self) -> str:
        joined = "\n".join(f"{e.relative_path}|{e.kind}|{e.size}|{e.digest}" for e in self.entries)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def fingerprint_tree(
    root: Path,
    read_bytes: Callable[[Path], bytes] = Path.read_bytes,
) -> CorpusFingerprint:
    """Walk ``root`` and return a content fingerprint.

    Rejects symlinks and non-regular files (``UnsafeCorpusEntry``). Read failures are
    reported as ``UnreadableCorpusEntry`` with a reason code only. Timestamps, ownership,
    and mode are intentionally excluded so metadata-only changes do not read as mutation.
    """
    entries: list[CorpusEntry] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise UnsafeCorpusEntry("symlink entry rejected")
        if path.is_dir():
            entries.append(CorpusEntry(rel, "dir", 0, ""))
            continue
        if not path.is_file():
            raise UnsafeCorpusEntry("non-regular entry rejected")
        with _redact_read_failures():  # never leak exc text
            data = read_bytes(path)
        entries.append(CorpusEntry(rel, "file", len(data), hashlib.sha256(data).hexdigest()))
    return CorpusFingerprint(tuple(entries))


def _run_dirs(corpus_dir: Path) -> list[Path]:
    return sorted(p for p in corpus_dir.iterdir() if p.is_dir() and (p / "raw").is_dir())


def corpus_status(corpus_dir: Path) -> str:
    """Classify a corpus root without echoing any path: 'ok' | 'absent' | 'empty' | 'wrong-layout'.

    - absent: the root does not exist or is not a directory.
    - empty: the root exists but contains nothing.
    - wrong-layout: the root has entries but no run directory holding a ``raw/`` subdir.
    - ok: at least one valid run directory is present.
    """
    if not corpus_dir.is_dir():
        return "absent"
    if _run_dirs(corpus_dir):
        return "ok"
    return "empty" if not any(corpus_dir.iterdir()) else "wrong-layout"


def raw_payload_multiset(run_dir: Path) -> collections.Counter[str]:
    """A filename-independent multiset of a run's raw ``data`` payloads, keyed by digest.

    Only digests are retained, so comparing two runs never materializes private content.
    """
    raw = run_dir / "raw"
    payloads = sorted(raw.glob("*.json")) if raw.is_dir() else []
    counter: collections.Counter[str] = collections.Counter()
    for payload in payloads:
        with _redact_read_failures():  # a bad/unreadable payload must not leak its path
            data = json.loads(payload.read_text(encoding="utf-8")).get("data")
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
        counter[hashlib.sha256(canonical.encode("utf-8")).hexdigest()] += 1
    return counter


def canonical_run_dirs(corpus_dir: Path) -> list[Path]:
    return _run_dirs(corpus_dir)


def raw_multisets_all_match(corpus_dir: Path) -> bool:
    """True when every run directory shares one raw-payload multiset (the SNAPSHOT invariant)."""
    runs = _run_dirs(corpus_dir)
    if len(runs) < 2:
        return False
    first = raw_payload_multiset(runs[0])
    return all(raw_payload_multiset(run) == first for run in runs[1:])


@dataclass(frozen=True, slots=True)
class PdfAggregate:
    source_pdfs: int
    pages: int
    attendees: int
    errors: int
    embedded_decodes: int
    rendered_decodes: int


def extract_pdf_aggregate(
    pdf_path: Path,
    *,
    dpis: tuple[int, ...] = (144, 200, 300, 400),
) -> PdfAggregate:
    """Aggregate-only PDF extraction facts. Imports the optional PDF stack lazily so the
    default lane never needs PyMuPDF/opencv. Never returns a name, value, or decoded URL."""
    import fitz
    from scoutmb.adapters.pdf.pages import extract_pdf

    with _redact_read_failures():  # PyMuPDF/pdf_to_scouts errors embed the real PDF path
        with fitz.open(pdf_path) as document:
            pages = document.page_count
        attendees, errors = extract_pdf(pdf_path, dpis, normalize_case=True, debug_dir=None)
    embedded = sum(1 for a in attendees if a.qr_decode_method.startswith("embedded-image"))
    rendered = sum(1 for a in attendees if a.qr_decode_method.startswith("rendered"))
    return PdfAggregate(
        source_pdfs=1,
        pages=pages,
        attendees=len(attendees),
        errors=len(errors),
        embedded_decodes=embedded,
        rendered_decodes=rendered,
    )


def find_single_pdf(corpus_dir: Path) -> Path:
    pdfs = sorted(corpus_dir.rglob("*.pdf"))
    if len(pdfs) != 1:
        raise UnreadableCorpusEntry(f"expected exactly one source PDF, found {len(pdfs)}")
    return pdfs[0]
