"""
Streaming XML -> slim Parquet, reading from a PIPE (7-Zip `-so` output) or a file.

Never requires the decompressed XML on disk. lxml.iterparse consumes the byte
stream incrementally; each <row> is reduced to the required attributes and
cleared immediately, so peak memory stays flat regardless of a 100-300 GB input.

USAGE (streamed from the .7z, nothing extracted to disk):
    7z x -so data\\raw\\stackoverflow.com.7z Posts.xml ^
      | python -m src.data_processing.extract_stream --which posts

USAGE (from an already-extracted file, e.g. on an external SSD):
    python -m src.data_processing.extract_stream --which posts --infile D:\\Posts.xml

USAGE (tiny smoke test from a local sample file):
    python -m src.data_processing.extract_stream --which posts --infile tests\\sample_posts.xml --limit 1000
"""
from __future__ import annotations
import argparse, os, sys, time, logging
import lxml.etree as ET
import pyarrow as pa
import pyarrow.parquet as pq

BATCH = 500_000  # rows per Parquet row group

FIELDS = {
    "posts":       ["Id", "PostTypeId", "OwnerUserId", "CreationDate",
                    "ParentId", "AcceptedAnswerId", "Tags"],
    "votes":       ["Id", "PostId", "VoteTypeId", "CreationDate"],
    "posthistory": ["Id", "PostHistoryTypeId", "PostId", "CreationDate", "UserId"],
}

def get_logger(which: str) -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    lg = logging.getLogger(f"extract.{which}")
    lg.setLevel(logging.INFO)
    if not lg.handlers:
        fh = logging.FileHandler(os.path.join("logs", f"extract_{which}.log"), encoding="utf-8")
        sh = logging.StreamHandler(sys.stderr)  # progress to stderr; data goes nowhere near stdout
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        fh.setFormatter(fmt); sh.setFormatter(fmt)
        lg.addHandler(fh); lg.addHandler(sh)
    return lg

def _flush(batch, fields, writer, out_path):
    cols = {f: pa.array([r[f] for r in batch], type=pa.string()) for f in fields}
    table = pa.table(cols)
    if writer is None:
        writer = pq.ParquetWriter(out_path, table.schema, compression="zstd")
    writer.write_table(table)
    return writer

def stream(source, out_path: str, fields: list[str], which: str,
           limit: int | None, log_every: int = 5_000_000):
    lg = get_logger(which)
    lg.info(f"START which={which} out={out_path} limit={limit}")
    t0 = time.time()
    writer = None
    batch, seen, kept = [], 0, 0
    # huge_tree lets lxml handle very large inputs; recover keeps going past minor glitches
    context = ET.iterparse(source, events=("end",), huge_tree=True, recover=True)
    try:
        for _, elem in context:
            if elem.tag != "row":
                continue
            seen += 1
            batch.append({f: elem.get(f) for f in fields})
            kept += 1
            elem.clear()
            # drop already-processed preceding siblings to keep the tree from growing
            while elem.getprevious() is not None:
                del elem.getparent()[0]
            if len(batch) >= BATCH:
                writer = _flush(batch, fields, writer, out_path); batch = []
            if seen % log_every == 0:
                rate = seen / max(time.time() - t0, 1e-9)
                lg.info(f"  {seen:,} rows  ({rate:,.0f}/s)")
            if limit is not None and seen >= limit:
                lg.info(f"  limit {limit} reached, stopping early"); break
        if batch:
            writer = _flush(batch, fields, writer, out_path)
    finally:
        if writer is not None:
            writer.close()
        del context
    dt = time.time() - t0
    lg.info(f"DONE which={which} rows={kept:,} elapsed={dt:,.1f}s -> {out_path}")
    print(f"OK {which}: {kept:,} rows -> {out_path}", file=sys.stderr)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--which", required=True, choices=list(FIELDS))
    ap.add_argument("--infile", default=None,
                    help="read from this file instead of stdin (optional)")
    ap.add_argument("--outdir", default="data/interim")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N rows (smoke test)")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    out_path = os.path.join(args.outdir, f"{args.which}.parquet")

    if args.infile:
        with open(args.infile, "rb") as fh:
            stream(fh, out_path, FIELDS[args.which], args.which, args.limit)
    else:
        # read the raw byte stream from stdin (7z -so pipe)
        stream(sys.stdin.buffer, out_path, FIELDS[args.which], args.which, args.limit)

if __name__ == "__main__":
    main()
