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

# ── Spanish month names ───────────────────────────────────────────────────────
SPANISH_MONTHS = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
    'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
    'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12,
    # Abbreviated (abr. → abr)
    'ene': 1, 'feb': 2, 'mar': 3, 'abr': 4,
    'may': 5, 'jun': 6, 'jul': 7, 'ago': 8,
    'sep': 9, 'set': 9, 'oct': 10, 'nov': 11, 'dic': 12,
}

# ── VAT table patterns (shared across vendors that use ES VAT format) ─────────
RE_VAT_ROW = re.compile(
    r'^\d+%\s+([\d,]+)\s+\S+\s+([\d,]+)',
    re.MULTILINE,
)
# Sage-style: "Base IVA % IVA Importe IVA\n160,00 21,00 33,60"
RE_VAT_TABLE_COL = re.compile(
    r'Base\s+IVA[^\n]*\n\s*([\d.,]+)\s+[\d.,]+\s+([\d.,]+)',
    re.IGNORECASE,
)
RE_TOTAL_PENDING = re.compile(r'Total\s+pendiente\s+([\d,]+)', re.IGNORECASE)
RE_INVOICE_NUM_GENERIC = re.compile(r'N[uú]mero\s+de\s+la\s+factura\s+([A-Z0-9]+)', re.IGNORECASE)


@dataclass
class InvoiceData:
    invoice_number: str | None = None
    date: datetime.date | None = None
    vendor_name: str | None = None
    excl_vat: float | None = None
    vat_amount: float | None = None
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
        if ',' in s:
            return float(s.replace('.', '').replace(',', '.'))
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
    m = pattern.search(text)
    if not m:
        return None
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
    month = int(g2) if g2.isdigit() else SPANISH_MONTHS.get(g2)
    year = int(m.group(3))
    if not month:
        return None
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def _extract_vat_table(text: str) -> tuple[float | None, float | None]:
    rows = RE_VAT_ROW.findall(text)
    if rows:
        excl = sum(_parse_number(r[0]) or 0.0 for r in rows)
        vat  = sum(_parse_number(r[1]) or 0.0 for r in rows)
        return round(excl, 2), round(vat, 2)
    m = RE_VAT_TABLE_COL.search(text)
    if m:
        excl = _parse_number(m.group(1))
        vat  = _parse_number(m.group(2))
        if excl is not None or vat is not None:
            return excl, vat
    m = RE_TOTAL_PENDING.search(text)
    if m:
        total = _parse_number(m.group(1))
        if total is not None:
            return total, 0.0
    return None, None


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

    if ftype in ('vat_table_base', 'vat_table_vat'):
        if 'vat' not in vat_cache:
            vat_cache['vat'] = _extract_vat_table(text)
        excl, vat = vat_cache['vat']
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
    )
    vat_cache: dict = {}
    fields_cfg: dict = vendor_cfg.get('fields', {})

    data.invoice_number = extract_field('invoice_number', fields_cfg.get('invoice_number', {}), text, vat_cache)
    data.date           = extract_field('date',           fields_cfg.get('date', {}),           text, vat_cache)
    data.vendor_name    = extract_field('vendor_name',    fields_cfg.get('vendor_name', {}),    text, vat_cache)
    data.excl_vat       = _parse_number(extract_field('excl_vat',   fields_cfg.get('excl_vat', {}),   text, vat_cache))
    data.vat_amount     = _parse_number(extract_field('vat_amount', fields_cfg.get('vat_amount', {}), text, vat_cache))

    for fname, val in [
        ('invoice_number', data.invoice_number),
        ('date',           data.date),
        ('excl_vat',       data.excl_vat),
        ('vat_amount',     data.vat_amount),
    ]:
        if val is None:
            data.warnings.append(f"Could not extract {fname}")

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
                text = page.extract_text() or ''
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

    return results


def extract_text_pages(pdf_path: Path) -> list[dict]:
    """
    Return raw extracted text per page — used by the vendor setup wizard.
    """
    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                pages.append({'page': i, 'text': page.extract_text() or ''})
    except Exception as exc:
        logging.error("Failed to read PDF %s: %s", pdf_path.name, exc)
    return pages
