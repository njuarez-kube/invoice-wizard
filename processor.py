"""
processor.py
PDF text extraction and field extraction engine.
Supports multiple vendors via JSON config files in vendors/.
"""

import re
import json
import logging
import datetime
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

# ── Month name → number (Spanish, English, French) ───────────────────────────
MONTH_NAMES = {
    # Spanish full
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
    # Spanish abbreviated
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'ago': 8,
    'sep': 9, 'set': 9, 'oct': 10, 'nov': 11, 'dic': 12,
    # English full
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    # English abbreviated
    'jan': 1, 'apr': 4, 'aug': 8, 'dec': 12,
    # French full
    'janvier': 1, 'fevrier': 2, 'fevr': 2,
    'avril': 4, 'mai': 5, 'juillet': 7, 'aout': 8,
    'octobre': 10, 'novembre': 11, 'decembre': 12,
    # French abbreviated
    'janv': 1, 'avr': 4, 'juil': 7, 'sept': 9, 'dec': 12,
}

# ── VAT table patterns (shared across vendors that use ES VAT format) ─────────
RE_VAT_ROW = re.compile(
    r'^(\d+(?:[.,]\d+)?)%\s+([\d,]+)\s+\S+\s+([\d,]+)',
    re.MULTILINE,
)
# Sage-style: "Base IVA % IVA Importe IVA\n160,00 21,00 33,60"
RE_VAT_TABLE_COL = re.compile(
    r'Base\s+IVA[^\n]*\n\s*([\d.,]+)\s+[\d.,]+\s+([\d.,]+)',
    re.IGNORECASE,
)
RE_TOTAL_PENDING = re.compile(r'Total\s+pendiente\s+([\d,]+)', re.IGNORECASE)
# Payflow-style: "153,62€ IVA 21% 32,26€ ..." (base€ IVA pct% vat€)
RE_VAT_INLINE = re.compile(
    r'([\d.,]+)€\s+IVA\s+(\d+(?:[.,]\d+)?)%\s+([\d.,]+)€',
    re.IGNORECASE,
)
RE_INVOICE_NUM_GENERIC = re.compile(r'N[uú]mero\s+de\s+la\s+factura\s+([A-Z0-9]+)', re.IGNORECASE)


def _clean_text(text: str) -> str:
    # strip em-dashes between non-space chars (two-column column-merge artifact)
    text = re.sub(r'(?<=\S)—(?=\S)', '', text)
    # strip spaces inserted within decimal numbers (two-column interleave artifact)
    # e.g. "5 60,00" → "560,00" ;  "1 17,60" → "117,60"
    # lookbehinds prevent joining two separate decimals (e.g. "319,56 13,24" must stay as-is)
    text = re.sub(r'(?<![,\.]\d)(?<![,\.])(\d) (\d+[,\.]\d)', r'\1\2', text)
    # strip space inserted before decimal separator
    # e.g. "3 .828,52" → "3.828,52" ;  "18 .231,06" → "18.231,06"
    text = re.sub(r'(\d) ([.,])(\d)', r'\1\2\3', text)
    return text


@dataclass
class InvoiceData:
    invoice_number: str | None = None
    date: datetime.date | None = None
    vendor_name: str | None = None
    excl_vat: float | None = None
    vat_amount: float | None = None
    vat_inc: float | None = None     # total VAT-inclusive amount if directly extracted
    retention: float | None = None   # IRPF retention (always positive); optional
    comments: str | None = None      # optional — only extracted if vendor config includes it
    vat_pct: float | None = None     # VAT % (e.g. 21.0); auto-computed when not in table
    currency: str = 'EUR'            # from vendor config
    # source metadata
    source_file: str = ""
    page_range: str = ""
    vendor_config_name: str = ""
    warnings: list[str] = field(default_factory=list)


# ── Number parsing ────────────────────────────────────────────────────────────
def _parse_number(s) -> float | None:
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    try:
        comma = s.rfind(',')
        dot   = s.rfind('.')
        if comma > dot:
            # European: 1.569,26 or 329,54 — comma is decimal
            return float(s.replace('.', '').replace(',', '.'))
        elif dot > comma:
            # UK/US: 1,569.26 or 329.54 — dot is decimal
            return float(s.replace(',', ''))
        else:
            # No separator at all
            return float(s)
    except ValueError:
        return None


# ── Field extraction strategies ───────────────────────────────────────────────
def _extract_regex(cfg: dict, text: str) -> str | None:
    try:
        pattern = re.compile(cfg['regex'], re.IGNORECASE | re.DOTALL)
    except re.error as exc:
        logging.warning("Invalid regex %r: %s", cfg.get('regex'), exc)
        return None
    occurrence = cfg.get('occurrence', 1)
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    m = matches[min(occurrence - 1, len(matches) - 1)]
    group = cfg.get('group', 1)
    try:
        return m.group(group).strip()
    except IndexError:
        return m.group(0).strip()


def _extract_spanish_dmy(cfg: dict, text: str) -> datetime.date | None:
    pattern = re.compile(cfg['regex'], re.IGNORECASE | re.DOTALL)
    m = pattern.search(text)
    if not m:
        return None
    day = int(m.group(1))
    g2 = m.group(2).lower().rstrip('.')
    month = int(g2) if g2.isdigit() else MONTH_NAMES.get(g2)
    year = int(m.group(3))
    if not month:
        return None
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _extract_english_mdy(cfg: dict, text: str) -> datetime.date | None:
    """Month-Day-Year: 'may 01, 2026' — groups: (month_word, day, year)."""
    pattern = re.compile(cfg['regex'], re.IGNORECASE | re.DOTALL)
    m = pattern.search(text)
    if not m:
        return None
    g1 = m.group(1).lower().rstrip('.')
    month = MONTH_NAMES.get(g1)
    day = int(m.group(2))
    year = int(m.group(3))
    if not month:
        return None
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _extract_vat_table(text: str) -> tuple[float | None, float | None, float | None]:
    rows = RE_VAT_ROW.findall(text)
    if rows:
        # groups: (pct, base, vat)
        excl = sum(_parse_number(r[1]) or 0.0 for r in rows)
        vat  = sum(_parse_number(r[2]) or 0.0 for r in rows)
        pct  = _parse_number(rows[0][0]) if len(rows) == 1 else None
        return round(excl, 2), round(vat, 2), pct
    m = RE_VAT_TABLE_COL.search(text)
    if m:
        excl = _parse_number(m.group(1))
        vat  = _parse_number(m.group(2))
        if excl is not None or vat is not None:
            return excl, vat, None
    rows = RE_VAT_INLINE.findall(text)   # groups: (base, pct, vat)
    if rows:
        excl = sum(_parse_number(r[0]) or 0.0 for r in rows)
        vat  = sum(_parse_number(r[2]) or 0.0 for r in rows)
        pct  = _parse_number(rows[0][1]) if len(rows) == 1 else None
        return round(excl, 2), round(vat, 2), pct
    m = RE_TOTAL_PENDING.search(text)
    if m:
        total = _parse_number(m.group(1))
        if total is not None:
            return total, 0.0, None
    return None, None, None


def extract_field(field_name: str, cfg: dict, text: str, vat_cache: dict) -> object:
    """
    Dispatch extraction by field type / presence of 'regex'.
    vat_cache holds (excl_vat, vat_amount) once computed to avoid double parsing.
    """
    ftype = cfg.get('type')

    if 'static' in cfg:
        return cfg['static']

    if ftype == 'spanish_dmy':
        return _extract_spanish_dmy(cfg, text)

    if ftype == 'english_mdy':
        return _extract_english_mdy(cfg, text)

    if ftype in ('vat_table_base', 'vat_table_vat'):
        if 'vat' not in vat_cache:
            vat_cache['vat'] = _extract_vat_table(text)
        excl, vat, _pct = vat_cache['vat']
        return excl if ftype == 'vat_table_base' else vat

    if 'regex' in cfg:
        return _extract_regex(cfg, text)

    return None


# ── Vendor loading & detection ────────────────────────────────────────────────
def load_vendors(vendors_dir: Path) -> list[dict]:
    vendors = []
    for p in sorted(vendors_dir.glob('*.json')):
        try:
            vendors.append(json.loads(p.read_text('utf-8')))
        except Exception as exc:
            logging.warning("Could not load vendor config %s: %s", p.name, exc)
    return vendors


def detect_vendor(text: str, vendors: list[dict]) -> dict | None:
    text_lower = text.lower()
    for v in vendors:
        if any(kw.lower() in text_lower for kw in v.get('detect_keywords', [])):
            return v
    return None


# ── Invoice extraction ────────────────────────────────────────────────────────
def extract_invoice(text: str, vendor_cfg: dict, source_file: str, page_range: str) -> InvoiceData:
    data = InvoiceData(
        source_file=source_file,
        page_range=page_range,
        vendor_config_name=vendor_cfg.get('name', ''),
        currency=vendor_cfg.get('currency', 'EUR'),
    )
    vat_cache: dict = {}
    fields_cfg: dict = vendor_cfg.get('fields', {})

    data.invoice_number = extract_field('invoice_number', fields_cfg.get('invoice_number', {}), text, vat_cache)
    data.date           = extract_field('date',           fields_cfg.get('date', {}),           text, vat_cache)
    data.vendor_name    = extract_field('vendor_name',    fields_cfg.get('vendor_name', {}),    text, vat_cache)
    data.excl_vat       = _parse_number(extract_field('excl_vat',   fields_cfg.get('excl_vat', {}),   text, vat_cache))
    data.vat_amount     = _parse_number(extract_field('vat_amount', fields_cfg.get('vat_amount', {}), text, vat_cache))

    if 'vat_inc' in fields_cfg:
        data.vat_inc = _parse_number(extract_field('vat_inc', fields_cfg.get('vat_inc', {}), text, vat_cache))

    if 'retention' in fields_cfg:
        raw = _parse_number(extract_field('retention', fields_cfg['retention'], text, vat_cache))
        if raw is not None:
            data.retention = abs(raw)

    if 'comments' in fields_cfg:
        data.comments = extract_field('comments', fields_cfg['comments'], text, vat_cache)

    # VAT %: use value from table if available, else compute from amounts
    if 'vat' not in vat_cache:
        vat_cache['vat'] = _extract_vat_table(text)
    _, _, pct = vat_cache['vat']
    if pct is not None:
        data.vat_pct = pct
    elif data.excl_vat and data.vat_amount and data.excl_vat > 0:
        data.vat_pct = round(data.vat_amount / data.excl_vat * 100, 1)

    for fname, val in [('invoice_number', data.invoice_number), ('date', data.date)]:
        if val is None:
            data.warnings.append(f"Could not extract {fname}")
    if data.vat_inc is None:
        for fname, val in [('excl_vat', data.excl_vat), ('vat_amount', data.vat_amount)]:
            if val is None:
                data.warnings.append(f"Could not extract {fname}")

    # cross-check: excl + vat should equal the total when all three are present
    # (skipped when retention is present — the PDF total may differ from our adjusted figure)
    if data.retention is None and data.vat_inc is not None and data.excl_vat is not None and data.vat_amount is not None:
        expected = round(data.excl_vat + data.vat_amount, 2)
        if abs(expected - data.vat_inc) > 0.02:
            data.warnings.append(
                f"Amount mismatch: excl({data.excl_vat}) + VAT({data.vat_amount})"
                f" = {expected}, but total = {data.vat_inc}"
            )

    return data


# ── Page grouping (multi-page invoice support) ────────────────────────────────
def _has_invoice_header(text: str, vendors: list[dict]) -> bool:
    """True if this page text contains an invoice number (any vendor pattern, or generic)."""
    if RE_INVOICE_NUM_GENERIC.search(text):
        return True
    for v in vendors:
        pattern_cfg = v.get('fields', {}).get('invoice_number', {})
        if 'regex' in pattern_cfg:
            try:
                if re.search(pattern_cfg['regex'], text, re.IGNORECASE):
                    return True
            except re.error:
                pass
    return False


def group_pages(pdf_path: Path, vendors: list[dict]) -> list[tuple[str, str]]:
    """
    Returns list of (combined_text, page_range_label) per invoice group.
    Consecutive pages without a new invoice header are merged into the previous group.
    """
    groups: list[tuple[list[str], list[int]]] = []   # (texts, page_nums)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = _clean_text(page.extract_text() or '')
                if _has_invoice_header(text, vendors):
                    groups.append(([text], [page_num]))
                elif groups:
                    groups[-1][0].append(text)
                    groups[-1][1].append(page_num)
                # pages before any invoice header are discarded
    except Exception as exc:
        logging.error("Failed to open PDF %s: %s", pdf_path.name, exc)
        return []

    result = []
    for texts, pages in groups:
        combined = '\n'.join(texts)
        label = f"p{pages[0]}" if len(pages) == 1 else f"p{pages[0]}-{pages[-1]}"
        result.append((combined, label))
    return result


# ── Duplicate-page merging ────────────────────────────────────────────────────
def _merge_same_invoice(invoices: list[InvoiceData]) -> list[InvoiceData]:
    """
    Multi-page invoices often repeat the invoice number on every page, causing
    group_pages to create one group per page.  Merge groups that share the same
    invoice number into a single InvoiceData, filling gaps from each page.
    """
    result: list[InvoiceData] = []
    seen: dict[str, InvoiceData] = {}   # invoice_number → first occurrence

    for inv in invoices:
        if not inv.invoice_number or inv.invoice_number not in seen:
            if inv.invoice_number:
                seen[inv.invoice_number] = inv
            result.append(inv)
            continue

        # Same invoice number already seen — merge into existing entry
        existing = seen[inv.invoice_number]
        for attr in ('date', 'vendor_name', 'excl_vat', 'vat_amount', 'vat_inc', 'retention', 'vat_pct', 'comments'):
            if getattr(existing, attr) is None:
                setattr(existing, attr, getattr(inv, attr))
        # Extend page range label
        if existing.page_range and inv.page_range and existing.page_range != inv.page_range:
            existing.page_range = f"{existing.page_range},{inv.page_range}"
        # Drop "Could not extract X" warnings that are now satisfied
        filled = {
            fname for fname in ('invoice_number', 'date', 'excl_vat', 'vat_amount')
            if getattr(existing, fname) is not None
        }
        existing.warnings = [
            w for w in existing.warnings
            if not any(w == f"Could not extract {f}" for f in filled)
        ]

    return result


# ── Main entry point ──────────────────────────────────────────────────────────
def process_pdf(pdf_path: Path, vendors: list[dict]) -> list[InvoiceData]:
    """
    Extract all invoices from a PDF. Returns one InvoiceData per invoice found.
    """
    results: list[InvoiceData] = []
    groups = group_pages(pdf_path, vendors)

    if not groups:
        logging.warning("No invoice pages found in %s", pdf_path.name)
        return results

    for text, page_range in groups:
        vendor_cfg = detect_vendor(text, vendors)
        if vendor_cfg is None:
            inv = InvoiceData(
                source_file=pdf_path.name,
                page_range=page_range,
                warnings=["No matching vendor config found"],
            )
            results.append(inv)
            logging.warning("%s %s — no vendor match", pdf_path.name, page_range)
            continue

        inv = extract_invoice(text, vendor_cfg, pdf_path.name, page_range)
        results.append(inv)

        logging.info(
            "%s %s | %s | %s | excl=%.2f | vat=%.2f",
            pdf_path.name, page_range,
            inv.invoice_number or '?',
            inv.date or '?',
            inv.excl_vat or 0.0,
            inv.vat_amount or 0.0,
        )

    return _merge_same_invoice(results)


def extract_text_pages(pdf_path: Path) -> list[dict]:
    """
    Return raw extracted text per page — used by the vendor setup wizard.
    """
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                pages.append({'page': i, 'text': _clean_text(page.extract_text() or '')})
    except Exception as exc:
        logging.error("Failed to read PDF %s: %s", pdf_path.name, exc)
    return pages
