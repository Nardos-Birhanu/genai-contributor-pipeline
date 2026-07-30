# Data Source

**Dataset:** Stack Exchange public data dump  Stack Overflow only
**Release:** 2025-03-31   **Access:** Internet Archive community mirror
**Archive:** `data/raw/stackoverflow.com.7z`

**Integrity (verified):**

7z t data/raw/stackoverflow.com.7z  ->  Everything is Ok
Files: 10
Archive compressed size:~68 GB
Total uncompressed: ~357 GB

Uncompressed member sizes:
- Posts.xml ~105 GB
- Votes.xml ~24 GB
- PostHistory.xml ~185 GB

**Handling:** files are NOT extracted to disk.
Processing streams each member from the archive via `7z -so` directly into a
Python parser; only slim Parquet is written. See docs/RUN_windows.md.

**Integrity to record after first run:**

SHA256 (stackoverflow.com.7z): E98C3850FE4249486E022A26F16AF5B76A29F36C63A0872191AC1B6B8C46812B
Download date:  2026-07-27

**Note:** Data were drawn from the Stack Exchange public data dump
(release 2025-03-31), Stack Overflow site, accessed via the Internet Archive
community mirror, under CC BY-SA 4.0. XML members were processed by streaming
decompression without full on-disk extraction.



