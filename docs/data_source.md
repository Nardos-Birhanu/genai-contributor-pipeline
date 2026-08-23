# Data Source

**Dataset:** Stack Exchange public data dump, Stack Overflow only
**Release date:** 2025-03-31   **Access:** Internet Archive
**Access:** `data/raw/stackoverflow.com.7z`

**Download URL:**  
https://archive.org/download/stackexchange_20250331/stackexchange_20250331/stackoverflow.com.7z

**Download command used:**
```bash
aria2c -x 16 -s 16 \
  "https://archive.org/download/stackexchange_20250331/stackexchange_20250331/stackoverflow.com.7z" \
  --dir=data/raw \
  --out=stackoverflow.com.7z
```

**Download date:** 2026-07-27  
**Local copy:** `data/raw/stackoverflow.com.7z` #Because file was big, didn't push it to the Github repo.

**SHA256 (verified):**  
(stackoverflow.com.7z): E98C3850FE4249486E022A26F16AF5B76A29F36C63A0872191AC1B6B8C46812B

Verify before running the pipeline:
```bash

# Windows (PowerShell)
Get-FileHash data\raw\stackoverflow.com.7z -Algorithm SHA256
```

**Archive integrity check:**
```bash
7z t data/raw/stackoverflow.com.7z   # -> Everything is Ok, Files: 10
```

**Sizes:**  
- compressed size:~68 GB
- Total uncompressed: ~357 GB
- Posts.xml ~104 GB
- Votes.xml ~24 GB
- PostHistory.xml ~181 GB

**Handling:** The XML files are not fully extracted to disk.

Each file is streamed directly from the archive using `7z -so` and processed by the Python parser. 
Only the resulting Parquet files are saved. See `RUN_windows.md` for the full run procedure.


**Note:** Data were used under the Stack Exchange CC BY-SA 4.0 license.



