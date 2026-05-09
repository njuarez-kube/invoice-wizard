# Invoice Processor

Local web application that extracts data from supplier invoice PDFs and appends rows to the **Facturas Kube** Excel file.  
Runs at `http://localhost:8080`. No internet connection required.

---

## What it does

| Step | Action |
|------|--------|
| 1 | Drag & drop one or more PDF invoices onto the dashboard |
| 2 | The app extracts invoice number, date, VAT amounts, and supplier name automatically |
| 3 | Review the extracted data in a table — edit any cell inline |
| 4 | Click **Write to Excel** — only columns B, C, F, G, H, K are filled |
| 5 | Download the updated `gastos.xlsx` |

New suppliers can be onboarded without touching any code via the **Add Vendor** wizard at `/setup`.

---

## Requirements

- **Python 3.10 or newer** — https://www.python.org/downloads/
  - During installation, check **"Add Python to PATH"**
- The **Facturas Kube.xlsx** template must be in the project folder (already included)

---

## Installation (first time only)

```bash
# 1. Open a terminal in the project folder
# 2. Install dependencies
pip install -r requirements.txt
```

That's it. No database, no Docker, no build step.

---

## Running locally

```bash
python main.py
```

The browser opens automatically at `http://localhost:8080`.  
To stop the server: press `Ctrl+C` in the terminal.

---

## Configuration — `config.ini`

All settings are in `config.ini`. Edit with any text editor.

```ini
[server]
host = 0.0.0.0        # 127.0.0.1 = local only  |  0.0.0.0 = network-visible
port = 8080           # change if port is in use
open_browser = true   # set to false on a headless server

[paths]
vendors_dir = vendors              # folder with supplier JSON configs
output      = output/gastos.xlsx   # where the Excel file is written
template    = Facturas Kube.xlsx   # base Excel template (do not modify)
done_dir    = done                 # legacy folder, not used in web mode
```

Paths can be relative (to the project folder) or absolute.

---

## Excel columns written

| Column | Letter | Field         |
|--------|--------|---------------|
| 2      | B      | Invoice No.   |
| 3      | C      | Date          |
| 6      | F      | € VAT inc.    |
| 7      | G      | VAT Return.   |
| 8      | H      | € VAT excl.   |
| 11     | K      | To / From     |

All other columns are left untouched. No cell colours are applied.

---

## Monthly workflow — Reset Excel

Click **Reset Excel** on the dashboard to delete the current `gastos.xlsx` and start fresh.  
Download the file first if you need to keep the current month's data.  
The next **Write to Excel** will create a new empty file from the template.

---

## Adding a new supplier

1. Go to `http://localhost:8080/setup`
2. Upload a sample invoice PDF from that supplier
3. Read the extracted PDF text that appears in Step 2
4. Fill in:
   - **Vendor name** — the display name written to the Excel
   - **Detection keywords** — words that appear in this supplier's PDFs (comma-separated)
5. For each field, copy the label text that appears just before the value in the PDF:
   - **Invoice Number** — pick *Code/text* or *Plain number*; check *"Value is on the line below"* if the label is a column header
   - **Invoice Date** — pick the date format that matches the PDF; check *"Value is on the line below"* if needed
   - **Vendor Name** — type the fixed text to write in every row
   - **Amount excl. VAT / VAT Amount** — try *Auto-detect* first (works for most Spanish invoices); switch to *Find by label* if auto-detect fails
6. Use the **Test** button on each field to verify the pattern against the uploaded PDF
7. Click **Save Vendor** — a new file is created in `vendors/<slug>.json`
8. The new supplier is immediately active on the dashboard

Vendor configs are plain JSON files. You can also edit them manually in `vendors/`.

### VAT table auto-detection

The auto-detect option handles two common formats:

| Format | Example |
|--------|---------|
| Standard ES | `21% 1.000,00 ... 210,00` (one line per VAT rate) |
| Column table | `Base IVA % IVA Importe IVA` header + `160,00 21,00 33,60` data row (Sage, etc.) |

### "Value is on the line below" option

Some invoices use a table layout where the label is a column header on one line and the value is on the line below:

```
Número   Fecha          Código cliente
MTA-263002-056837   27/04/2026   C-083907
```

Check *"Value is on the line below the label"* for Invoice Number and Date in these cases.

---

## Project structure

```
invoice-processor/
├── main.py               ← FastAPI app + all routes
├── processor.py          ← PDF text extraction engine
├── excel_writer.py       ← Excel read/write (columns B,C,F,G,H,K only)
├── config.ini            ← server and path settings
├── requirements.txt      ← Python dependencies
├── Facturas Kube.xlsx    ← Excel template (do not delete)
├── vendors/
│   └── amazon.json       ← Amazon ES vendor config
├── static/
│   ├── app.js            ← frontend logic (vanilla JS)
│   └── style.css
├── templates/
│   ├── index.html        ← dashboard
│   └── setup.html        ← vendor setup wizard
└── output/
    └── gastos.xlsx       ← generated output (created on first write)
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `python` not found | Reinstall Python and check "Add to PATH" |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` again |
| Port 8080 already in use | Change `port` in `config.ini`, or kill the old process: `netstat -ano \| findstr :8080` then `taskkill /PID <PID> /F` |
| Invoice not recognized | Go to `/setup` and add the supplier |
| Excel file is locked | Close `gastos.xlsx` in Excel before clicking Write |
| `No vendor` status badge | Supplier not in `vendors/` — use the Add Vendor wizard |
| Browser shows old UI after update | Hard-refresh with `Ctrl+Shift+R` to clear the cache |
| Date not extracted | Check the date format selected in the vendor config; use *Test* button to verify |
| Amounts not extracted | Try switching between *Auto-detect* and *Find by label* in the vendor config |

---

---

# Server Migration Guide

How to move this app from your local PC to a Linux server (Ubuntu/Debian).

## 1. Server requirements

- Ubuntu 20.04+ or Debian 11+ (any Linux with systemd works)
- Python 3.10+ (`python3 --version`)
- Open port 8080 (or whichever port you set in `config.ini`)
- At least 512 MB RAM

## 2. Copy the project to the server

```bash
# Option A — from your PC (run in PowerShell)
scp -r C:\Users\Nicolas\invoice-processor user@SERVER_IP:/opt/invoice-processor

# Option B — zip first, then copy and unzip on the server
# On your PC:
Compress-Archive -Path C:\Users\Nicolas\invoice-processor -DestinationPath invoice-processor.zip
scp invoice-processor.zip user@SERVER_IP:~
# On the server:
unzip ~/invoice-processor.zip -d /opt/invoice-processor
```

Replace `user` and `SERVER_IP` with your actual values.

## 3. Install Python and dependencies on the server

```bash
# On the server
sudo apt update && sudo apt install -y python3 python3-pip python3-venv

cd /opt/invoice-processor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 4. Update `config.ini` for server mode

```ini
[server]
host = 0.0.0.0    # expose on all interfaces
port = 8080
open_browser = false   # no browser on a headless server
```

## 5. Test it runs

```bash
source /opt/invoice-processor/venv/bin/activate
cd /opt/invoice-processor
python main.py
```

Open `http://SERVER_IP:8080` in your browser. If it works, stop it (`Ctrl+C`) and proceed.

## 6. Run as a system service (auto-start, auto-restart)

Create the service file:

```bash
sudo nano /etc/systemd/system/invoice-processor.service
```

Paste this (adjust `User` and paths if needed):

```ini
[Unit]
Description=Invoice Processor
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/invoice-processor
ExecStart=/opt/invoice-processor/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable invoice-processor
sudo systemctl start invoice-processor
sudo systemctl status invoice-processor   # should show "active (running)"
```

## 7. Open the firewall port

```bash
sudo ufw allow 8080/tcp
sudo ufw reload
```

Or if using a cloud provider (AWS, DigitalOcean, etc.), add an inbound rule for TCP port 8080 in the security group / firewall settings.

## 8. Optional — Put Nginx in front (recommended)

Nginx acts as a reverse proxy: users connect on port 80 (standard HTTP), Nginx forwards to port 8080. This also lets you add HTTPS later.

```bash
sudo apt install -y nginx

sudo nano /etc/nginx/sites-available/invoice-processor
```

```nginx
server {
    listen 80;
    server_name SERVER_IP;   # or your domain name

    client_max_body_size 50M;   # allow large PDF uploads

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/invoice-processor /etc/nginx/sites-enabled/
sudo nginx -t          # check config is valid
sudo systemctl restart nginx
```

Now the app is accessible at `http://SERVER_IP` (no port needed).

## 9. Optional — Add HTTPS with Let's Encrypt

Only works if you have a **domain name** pointing to the server.

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

Certbot updates the Nginx config automatically. Certificates renew automatically.

## 10. Updating the app

```bash
# Copy new files from your PC to the server
scp -r C:\Users\Nicolas\invoice-processor\*.py user@SERVER_IP:/opt/invoice-processor/
scp -r C:\Users\Nicolas\invoice-processor\static user@SERVER_IP:/opt/invoice-processor/
scp -r C:\Users\Nicolas\invoice-processor\templates user@SERVER_IP:/opt/invoice-processor/

# Restart the service
ssh user@SERVER_IP "sudo systemctl restart invoice-processor"
```

## 11. Backing up the Excel output and vendor configs

The two things that matter are:
- `output/gastos.xlsx` — the accumulated invoice data
- `vendors/*.json` — your supplier configurations

Back these up regularly:

```bash
# From your PC — download the current Excel file
scp user@SERVER_IP:/opt/invoice-processor/output/gastos.xlsx C:\Users\Nicolas\Desktop\

# Or set up a cron job on the server to copy to a backup folder daily
crontab -e
# Add: 0 2 * * * cp /opt/invoice-processor/output/gastos.xlsx /opt/invoice-processor/output/gastos_$(date +\%Y\%m\%d).xlsx
```

---

## Windows → Linux path differences

| Windows | Linux |
|---------|-------|
| `output\gastos.xlsx` | `output/gastos.xlsx` |
| `C:\Users\Nicolas\...` | `/home/ubuntu/...` or `/opt/...` |
| Backslash `\` | Forward slash `/` |

The app uses Python's `pathlib.Path` which handles both automatically. No code changes needed for Linux.
