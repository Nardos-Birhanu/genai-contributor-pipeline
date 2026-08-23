# Streaming Extraction Pipeline — Windows

## Overview

The Stack Overflow data dump contains very large XML files that cannot be efficiently loaded into memory.

This pipeline uses a streaming extraction approach:

7-Zip decompression --> XML stream (stdout) --> Python incremental XML parser --> Parquet output files



The XML members are streamed directly from 7-Zip into Python. The extractor reads one XML row at a time, keeps only the required attributes, and writes compact Parquet files for later analysis.

The raw Stack Overflow XML files are not stored in the repository.

## 1. Locate 7-Zip command line executable

The 7-Zip application may be installed without adding `7z.exe` to the system PATH.

Set a temporary session variable. But this variable is only available in the current terminal session.

```bat
set SZ="C:\Program Files\7-Zip\7z.exe"
```


## 2. Confirm archive contents

Before extraction, verify the internal filenames:

```bat
%SZ% l data\raw\stackoverflow.com.7z
```

Expected members:

Posts.xml
Votes.xml
PostHistory.xml


## 3. Activate environment

Activate the project environment:

bat
conda activate css_env



## 4. Run extraction smoke test

Before processing the complete dataset, run a small test:

bat
%SZ% x -so data\raw\stackoverflow.com.7z Posts.xml | python -m src.data_processing.extract_stream --which posts --limit 1000


Expected output:

OK posts: 1000 rows


Inspect the generated file:

bat
python -c "import pandas as pd; print(pd.read_parquet('data/interim/posts.parquet').head())"


Remove the test output before running the full extraction:

bat
del data\interim\posts.parquet



## 5. Full extraction

The extractor supports the main Stack Overflow XML members.

### Posts

bat
%SZ% x -so data\raw\stackoverflow.com.7z Posts.xml | python -m src.data_processing.extract_stream --which posts


### Votes

bat
%SZ% x -so data\raw\stackoverflow.com.7z Votes.xml | python -m src.data_processing.extract_stream --which votes


### PostHistory

bat
%SZ% x -so data\raw\stackoverflow.com.7z PostHistory.xml | python -m src.data_processing.extract_stream --which posthistory


The extraction produces:

data/
└── interim/
    ├── posts.parquet
    ├── votes.parquet
    └── posthistory.parquet


These generated datasets are intermediate outputs.



## 6. How the extraction works

The extractor avoids loading the complete XML file into memory. Instead, it processes the data incrementally:

Read XML row
      |
      v
Extract required attributes
      |
      v
Write batch to Parquet
      |
      v
Clear memory


This approach enables processing of very large Stack Overflow XML files without requiring the entire dataset to be loaded into memory, making the pipeline suitable for machines with limited RAM.


## 7. Notes and limitations

### Temporary disk usage

The XML members are not materialized as separate files. However, because the archive uses 7-Zip compression, decompression may require temporary working space.

Ensure sufficient disk space is available before running the full extraction.

### Pipeline failures

The extraction process does not support resuming a partially completed run.

If extraction fails:

1. Check the Python error message.
2. Verify the archive path.
3. Confirm that the smoke test succeeds.
4. Restart the extraction after fixing the issue.



## Output summary

After successful extraction:

Raw Stack Overflow dump
          |
          v
Streaming XML extraction
          |
          v
Parquet intermediate datasets


These Parquet files are used in later stages for validation and analytical dataset construction.
