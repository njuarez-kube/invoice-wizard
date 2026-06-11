import zipfile, pathlib

INCLUDE = [
    "main.py", "processor.py", "excel_writer.py", "gdrive.py",
    "config.ini", "requirements.txt", "Facturas Kube.xlsx",
    "token.json", "icon.ico", "version.txt",
    "install.bat", "start.bat", "check.bat", "update.bat", "update.ps1",
    "create-shortcut.bat", "INSTRUCTIONS.html",
]
INCLUDE_DIRS = ["vendors", "templates", "static"]

out = pathlib.Path("The_Invoice_Wizard.zip")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in INCLUDE:
        p = pathlib.Path(f)
        if p.exists():
            zf.write(p)
        else:
            print(f"  WARNING: {f} not found, skipped")
    for d in INCLUDE_DIRS:
        for p in pathlib.Path(d).rglob("*"):
            if p.is_file():
                zf.write(p)

print(f"Created {out} ({out.stat().st_size // 1024} KB)")
