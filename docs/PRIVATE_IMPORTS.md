# Private Vacancy Imports

The repository is Private, but personal source files and generated evidence still remain local and are excluded by `.gitignore`.

## Supported files

- Text: `.txt`, `.md`, `.csv`
- PDF: `.pdf`
- Word: `.docx`
- Email: `.eml`
- Image OCR: `.png`, `.jpg`, `.jpeg`, `.webp`, `.tif`, `.tiff`, `.bmp`

Macro-enabled Word files and executable files are not accepted. Symbolic-link inputs are rejected.

## Single file

```powershell
job-intel --db data/database/jobs.db import-file `
  --file private-input\vacancy.pdf `
  --title "Senior Piping Engineer" `
  --company "Example EPC" `
  --location "Mumbai" `
  --evidence-dir private-output\evidence `
  --output data\exports\Piping_E3D_Jobs.xlsx
```

Title and company may be omitted, but the record is then marked `review_required`. Inferred values and OCR output must be reviewed before use.

## Folder import

```powershell
job-intel --db data/database/jobs.db import-folder `
  --folder private-input `
  --recursive `
  --evidence-dir private-output\evidence `
  --output data\exports\Piping_E3D_Jobs.xlsx
```

The folder importer isolates failures: one unreadable file does not discard other valid files. It returns exit `1` when one or more files fail and exit `2` for a fatal import or workbook failure.

## OCR

Image import requires `--ocr`. Tesseract OCR must be installed on the Windows computer.

```powershell
job-intel --db data/database/jobs.db import-file `
  --file private-input\job-screenshot.png `
  --ocr `
  --tesseract-cmd "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

OCR-derived jobs always enter `review_required`. PDF text is extracted with `pypdf`; a scanned PDF with no embedded text is rejected with an OCR/manual-review message rather than creating an empty or invented job.

## Evidence and duplicate protection

- Each source file is SHA-256 hashed.
- The original file is copied into `private-output/evidence/<hash-prefix>/`.
- The copied file is hashed again before it is accepted.
- Re-importing the same bytes reports `duplicate` and does not create another job.
- `private_imports` records extraction method, file size, hash, evidence path, review status and linked job key.
- `job-intel verify` checks every private evidence file, hash, import state and linked job.
- Excel contains `Private_Imports` and routes uncertain records to `Manual_Review`.

## One-command Windows runner

Place vacancy files in `private-input`, then run:

```powershell
.\scripts\run_private_import.ps1
```

For image OCR:

```powershell
.\scripts\run_private_import.ps1 `
  -EnableOcr `
  -TesseractCommand "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

## Windows daily task

The installer creates a per-user task that runs only while the Windows user is logged in. It uses the computer's local time.

```powershell
.\scripts\install_private_import_task.ps1 -DailyTime "09:30"
```

Installing the Windows task must be done on the user's computer; GitHub cannot change Windows Task Scheduler remotely.

## Privacy rules

- Do not commit `private-input`, `private-output`, databases, workbooks, PDFs, Word files, email files or screenshots.
- Do not upload CVs or application records into GitHub Actions artifacts.
- Public-source GitHub automation and private local imports remain separate.
- Email addresses found in supplied files are stored only as `PUBLIC_UNVERIFIED`.
- Missing salary, employer, location or experience data is never invented.
