"""
main.py
FastAPI web application for the Invoice Processor.
Run: python main.py
Open: http://localhost:8080
"""

import configparser
import json
import os
import re
import logging
import signal
import tempfile
import threading
import webbrowser
from pathlib import Path

import urllib.request

import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import processor
import excel_writer
import gdrive

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
_cfg = configparser.ConfigParser()
_cfg.read(BASE_DIR / 'config.ini', encoding='utf-8')

def _path(key: str, fallback: str) -> Path:
    raw = _cfg.get('paths', key, fallback=fallback)
    p = Path(raw)
    return p if p.is_absolute() else BASE_DIR / p

VENDORS_DIR   = _path('vendors_dir', 'vendors')
OUTPUT_PATH   = _path('output',      'output/gastos.xlsx')
TEMPLATE_PATH = _path('template',    'Facturas Kube.xlsx')
DONE_DIR      = _path('done_dir',    'done')

_gdrive_token_raw = _cfg.get('gdrive', 'token',      fallback='token.json')
_GDRIVE_TOKEN     = str(BASE_DIR / _gdrive_token_raw) if not Path(_gdrive_token_raw).is_absolute() else _gdrive_token_raw
_GDRIVE_FOLDER_ID = _cfg.get('gdrive', 'folder_id',   fallback='')
TEMPLATES_DIR = BASE_DIR / 'templates'

_HOST         = _cfg.get('server', 'host',               fallback='0.0.0.0')
_PORT         = _cfg.getint('server', 'port',            fallback=8080)
_OPEN_BROWSER = _cfg.getboolean('server', 'open_browser', fallback=True)

DONE_DIR.mkdir(exist_ok=True)
OUTPUT_PATH.parent.mkdir(exist_ok=True)

# ── Update check ──────────────────────────────────────────────────────────────
_LOCAL_VERSION = (BASE_DIR / 'version.txt').read_text(encoding='utf-8').strip() \
    if (BASE_DIR / 'version.txt').exists() else ''
_GITHUB_REPO   = _cfg.get('update', 'github_repo', fallback='').strip()
_update_cache: dict = {}

def _fetch_latest_version():
    if not _GITHUB_REPO:
        return
    try:
        url = f'https://raw.githubusercontent.com/{_GITHUB_REPO}/main/version.txt'
        with urllib.request.urlopen(url, timeout=5) as r:
            latest = r.read().decode().strip()
        _update_cache['latest']    = latest
        _update_cache['available'] = (latest != _LOCAL_VERSION)
    except Exception:
        pass

threading.Thread(target=_fetch_latest_version, daemon=True).start()

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Invoice Processor")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    ico = BASE_DIR / "icon.ico"
    if ico.exists():
        return FileResponse(ico)
    return FileResponse(BASE_DIR / "static" / "icon.ico") if (BASE_DIR / "static" / "icon.ico").exists() else HTMLResponse("", status_code=404)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


# ── Shutdown ──────────────────────────────────────────────────────────────────
@app.post("/api/shutdown", include_in_schema=False)
async def shutdown():
    def _stop():
        import time
        time.sleep(0.3)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_stop, daemon=True).start()
    return JSONResponse({"status": "ok"})


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse((TEMPLATES_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/setup", response_class=HTMLResponse)
async def setup_page():
    return HTMLResponse((TEMPLATES_DIR / "setup.html").read_text(encoding="utf-8"))


# ── API: Extract invoices from uploaded PDFs ──────────────────────────────────
@app.post("/api/extract")
async def extract(files: list[UploadFile] = File(...)):
    try:
        vendors = processor.load_vendors(VENDORS_DIR)
        seen    = excel_writer.load_existing_invoice_numbers(OUTPUT_PATH)
    except Exception as exc:
        logging.error("Startup error in extract: %s", exc, exc_info=True)
        return JSONResponse(content={'rows': [], 'error': str(exc)})
    results = []

    for upload in files:
        if not upload.filename.lower().endswith('.pdf'):
            continue

        content = await upload.read()
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            invoices = processor.process_pdf(tmp_path, vendors)
        except Exception as exc:
            logging.error("Error processing %s: %s", upload.filename, exc, exc_info=True)
            invoices = []
            results.append({
                'source_file': upload.filename, 'page_range': '', 'invoice_number': None,
                'date': None, 'vendor_name': None, 'excl_vat': None, 'vat_amount': None,
                'vat_inc': 0, 'vendor_config': None, 'duplicate': False,
                'warnings': [f"Processing error: {exc}"],
            })
        finally:
            tmp_path.unlink(missing_ok=True)

        for inv in invoices:
            is_dup = bool(inv.invoice_number and (inv.invoice_number, inv.vendor_name or '') in seen)
            vat_inc_raw = inv.vat_inc if inv.vat_inc is not None else round((inv.excl_vat or 0) + (inv.vat_amount or 0), 2)
            if inv.retention is not None and inv.excl_vat is not None and inv.vat_amount is not None:
                vat_inc_display = round(inv.excl_vat + inv.vat_amount - inv.retention, 2)
            else:
                vat_inc_display = vat_inc_raw
            results.append({
                'source_file':    upload.filename,
                'page_range':     inv.page_range,
                'invoice_number': inv.invoice_number,
                'date':           inv.date.isoformat() if inv.date else None,
                'vendor_name':    inv.vendor_name,
                'excl_vat':       inv.excl_vat,
                'vat_amount':     inv.vat_amount,
                'vat_inc':        vat_inc_display,
                'retention':      inv.retention,
                'vendor_config':  inv.vendor_config_name,
                'vat_pct':        inv.vat_pct,
                'currency':       inv.currency,
                'comments':       inv.comments,
                'warnings':       inv.warnings,
                'duplicate':      is_dup,
            })

    return JSONResponse(content={'rows': results})


# ── API: Write confirmed rows to Excel ────────────────────────────────────────
class InvoiceRow(BaseModel):
    source_file: str = ''
    page_range: str = ''
    invoice_number: str | None = None
    date: str | None = None          # ISO date string or None
    vendor_name: str | None = None
    excl_vat: float | None = None
    vat_amount: float | None = None
    vat_inc: float | None = None
    retention: float | None = None
    vat_pct: float | None = None
    currency: str = 'EUR'
    comments: str | None = None

class WriteRequest(BaseModel):
    rows: list[InvoiceRow]


@app.post("/api/write")
async def write_excel(body: WriteRequest):
    import datetime as dt

    seen = excel_writer.load_existing_invoice_numbers(OUTPUT_PATH)
    invoices = []

    for r in body.rows:
        date_val = None
        if r.date:
            try:
                date_val = dt.date.fromisoformat(r.date)
            except ValueError:
                pass

        inv = processor.InvoiceData(
            invoice_number=r.invoice_number,
            date=date_val,
            vendor_name=r.vendor_name,
            excl_vat=r.excl_vat,
            vat_amount=r.vat_amount,
            vat_inc=r.vat_inc,
            retention=r.retention,
            vat_pct=r.vat_pct,
            currency=r.currency,
            comments=r.comments,
            source_file=r.source_file,
            page_range=r.page_range,
        )
        invoices.append(inv)

    summary = excel_writer.append_rows(OUTPUT_PATH, TEMPLATE_PATH, invoices, seen)
    return JSONResponse(content=summary)


# ── API: Download Excel ───────────────────────────────────────────────────────
@app.get("/api/excel")
async def download_excel():
    if not OUTPUT_PATH.exists():
        raise HTTPException(status_code=404, detail="No Excel file yet")
    return FileResponse(
        path=OUTPUT_PATH,
        filename="gastos.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ── API: Reset Excel ──────────────────────────────────────────────────────────
@app.delete("/api/excel")
async def reset_excel():
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()
        logging.info("Output Excel reset by user")
    return JSONResponse(content={'reset': True})


# ── API: Vendors ──────────────────────────────────────────────────────────────
@app.get("/api/vendors")
async def list_vendors():
    vendors = processor.load_vendors(VENDORS_DIR)
    return JSONResponse(content={'vendors': vendors})


@app.post("/api/vendors")
async def save_vendor(request: Request):
    body = await request.json()
    name = body.get('name', '').strip()
    if not name:
        raise HTTPException(status_code=400, detail="Vendor name is required")

    slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    path = VENDORS_DIR / f"{slug}.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding='utf-8')
    return JSONResponse(content={'slug': slug, 'path': str(path)})


# ── API: Vendor setup — extract sample PDF text ───────────────────────────────
@app.post("/api/vendors/sample-text")
async def sample_text(file: UploadFile = File(...)):
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        pages = processor.extract_text_pages(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return JSONResponse(content={'pages': pages})


# ── API: Test a regex against text ────────────────────────────────────────────
class TestRegexRequest(BaseModel):
    regex: str
    text: str
    group: int = 1
    occurrence: int = 1

@app.post("/api/vendors/test")
async def test_regex(body: TestRegexRequest):
    try:
        pattern = re.compile(body.regex, re.IGNORECASE | re.DOTALL)
        matches = list(pattern.finditer(body.text))
        if matches:
            m = matches[min(body.occurrence - 1, len(matches) - 1)]
            captured = m.group(body.group) if body.group <= len(m.groups()) else m.group(0)
            return JSONResponse(content={'match': True, 'captured': captured.strip()})
        return JSONResponse(content={'match': False, 'captured': None})
    except re.error as exc:
        return JSONResponse(content={'match': False, 'captured': None, 'error': str(exc)})


# ── API: Google Drive sync ────────────────────────────────────────────────────
@app.get("/api/drive/status")
async def drive_status():
    status = gdrive.get_status(_GDRIVE_TOKEN)
    return JSONResponse(content=status)


@app.post("/api/drive/pull")
async def drive_pull():
    service = gdrive.authenticate_gdrive(_GDRIVE_TOKEN)
    if service is None:
        return JSONResponse(content={'error': 'Drive not connected'}, status_code=503)
    result = gdrive.pull_vendors(service, _GDRIVE_FOLDER_ID, VENDORS_DIR)
    logging.info("Drive pull: %s", result)
    return JSONResponse(content=result)


@app.post("/api/drive/push")
async def drive_push():
    service = gdrive.authenticate_gdrive(_GDRIVE_TOKEN)
    if service is None:
        return JSONResponse(content={'error': 'Drive not connected'}, status_code=503)
    result = gdrive.push_vendors(service, _GDRIVE_FOLDER_ID, VENDORS_DIR)
    logging.info("Drive push: %s", result)
    return JSONResponse(content=result)


# ── API: Version / update check ──────────────────────────────────────────────
@app.get('/api/version')
async def api_version():
    return JSONResponse(content={
        'local':     _LOCAL_VERSION,
        'latest':    _update_cache.get('latest', ''),
        'available': _update_cache.get('available', False),
    })


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if _OPEN_BROWSER:
        webbrowser.open(f'http://localhost:{_PORT}')
    uvicorn.run("main:app", host=_HOST, port=_PORT, reload=False)
