"""
gdrive.py
Google Drive sync for vendor configs.
Function names mirror api_gdrive.ipynb exactly.
"""

import json
import io
import logging
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive']


# ── Core functions (same signatures as api_gdrive.ipynb) ─────────────────────

def authenticate_gdrive(token_path: str = 'token.json'):
    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build('drive', 'v3', credentials=creds)
    except FileNotFoundError:
        logging.warning("token.json not found: %s", token_path)
        return None
    except Exception as exc:
        logging.error("Drive auth error: %s", exc)
        return None


def list_files_in_folder(service, folder_id: str) -> dict:
    """Returns {vendor_slug: file_id} for all .json files in the Drive folder."""
    try:
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query,
            pageSize=1000,
            fields="nextPageToken, files(id, name)"
        ).execute()

        vendor_file_ids = {}
        for item in results.get('files', []):
            file_name = item['name']
            file_id   = item['id']
            vendor_slug = file_name.replace('.json', '')
            vendor_file_ids[vendor_slug] = file_id
        return vendor_file_ids

    except Exception as exc:
        logging.error("list_files_in_folder error: %s", exc)
        return {}


def read_json_from_drive(service, file_id: str) -> dict | None:
    """Downloads a JSON file from Drive and returns it as a Python dict."""
    try:
        request     = service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader  = MediaIoBaseDownload(file_buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return json.loads(file_buffer.getvalue().decode('utf-8'))
    except Exception as exc:
        logging.error("read_json_from_drive error: %s", exc)
        return None


def upload_dict_to_drive(service, folder_id: str, data_dict: dict, drive_file_name: str) -> str:
    """Uploads a dict as a JSON file to Drive. Updates if it exists, creates if not.
    Raises on failure so the caller can include the message in its error list."""
    json_bytes  = json.dumps(data_dict, ensure_ascii=False, indent=2).encode('utf-8')
    file_stream = io.BytesIO(json_bytes)
    media       = MediaIoBaseUpload(file_stream, mimetype='application/json', resumable=True)

    query = f"'{folder_id}' in parents and name='{drive_file_name}' and trashed=false"
    existing = service.files().list(q=query, fields='files(id, name)').execute().get('files', [])

    if existing:
        result = service.files().update(
            fileId=existing[0]['id'],
            media_body=media,
            fields='id, name'
        ).execute()
        logging.info("Drive: updated '%s'", result.get('name'))
        return result.get('id')
    else:
        result = service.files().create(
            body={'name': drive_file_name, 'parents': [folder_id]},
            media_body=media,
            fields='id, name'
        ).execute()
        logging.info("Drive: created '%s'", result.get('name'))
        return result.get('id')


# ── FastAPI wrapper functions ─────────────────────────────────────────────────

def get_status(token_path: str) -> dict:
    service = authenticate_gdrive(token_path)
    if service is None:
        return {'connected': False, 'message': f'token.json not found: {token_path}'}
    try:
        service.files().list(pageSize=1, fields='files(id)').execute()
        return {'connected': True, 'message': 'Connected'}
    except HttpError as exc:
        return {'connected': False, 'message': str(exc)}


def pull_vendors(service, folder_id: str, vendors_dir: Path) -> dict:
    """Download all vendor JSONs from Drive into vendors_dir."""
    vendor_file_ids = list_files_in_folder(service, folder_id)
    updated = created = 0
    errors  = []

    for vendor_slug, file_id in vendor_file_ids.items():
        data = read_json_from_drive(service, file_id)
        if data is None:
            errors.append(f"Could not read {vendor_slug} from Drive")
            continue
        dest = vendors_dir / f"{vendor_slug}.json"
        existed = dest.exists()
        try:
            dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            if existed:
                updated += 1
            else:
                created += 1
        except Exception as exc:
            errors.append(f"Could not write {vendor_slug}.json: {exc}")

    return {'updated': updated, 'created': created, 'errors': errors}


def push_vendors(service, folder_id: str, vendors_dir: Path) -> dict:
    """Upload all local vendor JSONs from vendors_dir to Drive."""
    updated = created = 0
    errors  = []

    vendor_file_ids = list_files_in_folder(service, folder_id)

    for path in sorted(vendors_dir.glob('*.json')):
        vendor_slug     = path.stem
        drive_file_name = f"{vendor_slug}.json"
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:
            errors.append(f"Could not read {path.name}: {exc}")
            continue

        try:
            upload_dict_to_drive(service, folder_id, data, drive_file_name)
            if vendor_slug in vendor_file_ids:
                updated += 1
            else:
                created += 1
        except Exception as exc:
            logging.error("push_vendors: failed to upload %s: %s", drive_file_name, exc)
            errors.append(f"{drive_file_name}: {exc}")

    return {'updated': updated, 'created': created, 'errors': errors}
