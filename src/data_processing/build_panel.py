"""
Stages 4-6: cohorts + acceptance reconstruction + panel assembly, in DuckDB over
the interim Parquet produced by extract_stream.py. Streams via Parquet, so it does
not load the full tables into Python memory.

USAGE:
    python -m src.data_processing.build_panel
"""
from __future__ import annotations
import os, yaml, duckdb

def load_cfg(p="config/config.yaml"):
    with open(p) as f: return yaml.safe_load(f)

def build(cfg):
    interim = cfg["paths"]["interim_dir"]
    processed = cfg["paths"]["processed_dir"]
    os.makedirs(processed, exist_ok=True)
    posts = os.path.join(interim, "posts.parquet")
    votes = os.path.join(interim, "votes.parquet")
    tdate = cfg["design"]["treatment_date"]
    window = cfg["design"]["conversion_window_months"]
    acc_vt = cfg["design"]["accepted_vote_type"]
    out = os.path.join(processed, "analysis_panel.parquet")

    con = duckdb.connect()
    con.execute("PRAGMA threads=4;")
    con.execute(f"""
        CREATE VIEW posts AS
        SELECT TRY_CAST(Id AS BIGINT) AS post_id,
               TRY_CAST(PostTypeId AS INT) AS post_type,
               TRY_CAST(OwnerUserId AS BIGINT) AS user_id,
               TRY_CAST(CreationDate AS TIMESTAMP) AS created,
               TRY_CAST(ParentId AS BIGINT) AS parent_id,
               TRY_CAST(AcceptedAnswerId AS BIGINT) AS accepted_answer_id
        FROM read_parquet('{posts}')
        WHERE OwnerUserId IS NOT NULL;
    """)
    con.execute(f"""
        CREATE VIEW acc_votes AS
        SELECT TRY_CAST(PostId AS BIGINT) AS post_id,
               TRY_CAST(CreationDate AS TIMESTAMP) AS accept_date
        FROM read_parquet('{votes}')
        WHERE TRY_CAST(VoteTypeId AS INT) = {acc_vt};
    """)
    con.execute("""
        CREATE VIEW entry AS
        SELECT user_id, MIN(created) AS first_post_date
        FROM posts WHERE post_type IN (1,2) GROUP BY user_id;
    """)
    con.execute("""
        CREATE VIEW user_accepted_answers AS
        SELECT p.user_id, p.created AS answer_created, v.accept_date
        FROM posts p JOIN acc_votes v ON p.post_id = v.post_id
        WHERE p.post_type = 2;
    """)
    con.execute("""
        CREATE VIEW first_answer AS
        SELECT user_id, MIN(created) AS first_answer_date
        FROM posts WHERE post_type = 2 GROUP BY user_id;
    """)
    con.execute(f"""
        CREATE VIEW final AS
        WITH first_acc AS (
            SELECT user_id,
                   MIN(answer_created) AS faa_created,
                   MIN(accept_date)    AS faa_accept
            FROM user_accepted_answers GROUP BY user_id
        )
        SELECT
            e.user_id,
            strftime(e.first_post_date, '%Y-%m') AS cohort_month,
            CASE WHEN e.first_post_date < TIMESTAMP '{tdate}' THEN 'pre' ELSE 'post' END AS cohort_period,
            e.first_post_date,
            fa.first_answer_date,
            fac.faa_created, fac.faa_accept,
            e.first_post_date + INTERVAL '{window}' MONTH AS window_end,
            -- primary event (option a: answer creation) within window
            CASE WHEN fac.faa_created IS NOT NULL AND fac.faa_created <= e.first_post_date + INTERVAL '{window}' MONTH
                 THEN 1 ELSE 0 END AS event_primary,
            CASE WHEN fac.faa_created IS NOT NULL AND fac.faa_created <= e.first_post_date + INTERVAL '{window}' MONTH
                 THEN date_diff('day', e.first_post_date, fac.faa_created)
                 ELSE date_diff('day', e.first_post_date, e.first_post_date + INTERVAL '{window}' MONTH) END AS time_primary_days,
            -- secondary: first answer within window
            CASE WHEN fa.first_answer_date IS NOT NULL AND fa.first_answer_date <= e.first_post_date + INTERVAL '{window}' MONTH
                 THEN 1 ELSE 0 END AS event_secondary,
            CASE WHEN fa.first_answer_date IS NOT NULL AND fa.first_answer_date <= e.first_post_date + INTERVAL '{window}' MONTH
                 THEN date_diff('day', e.first_post_date, fa.first_answer_date)
                 ELSE date_diff('day', e.first_post_date, e.first_post_date + INTERVAL '{window}' MONTH) END AS time_secondary_days,
            -- sensitivity (option b: acceptance date)
            CASE WHEN fac.faa_accept IS NOT NULL AND fac.faa_accept <= e.first_post_date + INTERVAL '{window}' MONTH
                 THEN date_diff('day', e.first_post_date, fac.faa_accept)
                 ELSE date_diff('day', e.first_post_date, e.first_post_date + INTERVAL '{window}' MONTH) END AS time_primary_acceptdate_days
        FROM entry e
        LEFT JOIN first_answer fa ON e.user_id = fa.user_id
        LEFT JOIN first_acc  fac ON e.user_id = fac.user_id;
    """)
    con.execute(f"COPY final TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD);")
    n = con.execute("SELECT COUNT(*) FROM final").fetchone()[0]
    conv = con.execute("SELECT AVG(event_primary) FROM final").fetchone()[0]
    print(f"panel rows: {n:,}   overall primary conversion: {conv:.4f}   -> {out}")
    con.close()

if __name__ == "__main__":
    build(load_cfg())
