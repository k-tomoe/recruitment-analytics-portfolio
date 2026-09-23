from pathlib import Path

import sqlite3

import pandas as pd


# =========================================================
# パス設定
# =========================================================

RAW_DIR = Path("data/raw")
DATABASE_DIR = Path("database")

DATABASE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

DB_PATH = (
    DATABASE_DIR
    / "recruitment_analytics.sqlite"
)


# =========================================================
# 修正① CSVファイルとテーブル名の対応
# =========================================================
#
# 【変更前】
#
# candidates_test.csv
# candidate_experiences_test.csv
# candidate_preferences_test.csv
# jobs_test.csv
# ...
#
#
# 【問題点】
#
# 小規模テスト用ファイルをSQLiteへ
# 取り込む構成になっていた。
#
#
# 【修正仕様】
#
# すべて分析用正式CSVへ切り替える。
#
# applications.csvには今回追加した
#
# withdrawal_stage
#
# も含まれるため、
# pandas.read_csv() → to_sql() により
# SQLite側にも自動的に列が作成される。
# =========================================================

tables = {
    "clients":
        "clients.csv",

    "recruiters":
        "recruiters.csv",

    "occupations":
        "occupations.csv",

    "locations":
        "locations.csv",

    "candidates":
        "candidates.csv",

    "candidate_experiences":
        "candidate_experiences.csv",

    "candidate_preferences":
        "candidate_preferences.csv",

    "jobs":
        "jobs.csv",

    "job_entries":
        "job_entries.csv",

    "candidate_activities":
        "candidate_activities.csv",

    "job_introductions":
        "job_introductions.csv",

    "applications":
        "applications.csv",

    "workplace_visits":
        "workplace_visits.csv",

    "placements":
        "placements.csv",
}


# =========================================================
# 修正② 必要CSVがすべて存在することを先に確認
# =========================================================
#
# 【変更前】
#
# forループの途中でファイルが存在しなければ
# FileNotFoundErrorとしていた。
#
#
# 【問題点】
#
# 途中までSQLiteへロードした後に
# ファイル不足へ気付く可能性がある。
#
#
# 【修正仕様】
#
# DB作成前に全CSVの存在を確認する。
#
# 1ファイルでも不足していれば
# SQLite再構築を開始しない。
# =========================================================

missing_files = []


for file_name in tables.values():

    csv_path = (
        RAW_DIR
        / file_name
    )

    if not csv_path.exists():

        missing_files.append(
            str(
                csv_path
            )
        )


if len(
    missing_files
) > 0:

    missing_text = "\n".join(
        missing_files
    )

    raise FileNotFoundError(
        "必要なCSVファイルが不足しています。\n"
        f"{missing_text}"
    )


# =========================================================
# 修正③ 既存SQLiteを一度削除
# =========================================================
#
# 【変更前】
#
# 既存DBへ接続し、
# rawテーブルだけをif_exists="replace"していた。
#
#
# 【問題点】
#
# 以前作成した、
#
# mart_job_analysis
# mart_application_analysis
#
# などがDB内に残る可能性がある。
#
# rawだけ新しく、
# martだけ古い状態になると、
# 分析結果の不整合につながる。
#
#
# 【修正仕様】
#
# 今回はraw CSVから分析DBを
# 完全再構築する。
#
# 既存SQLiteが存在する場合は削除してから
# 新しく作成する。
#
# martはこの後SQLから再作成する。
# =========================================================

if DB_PATH.exists():

    DB_PATH.unlink()

    print(
        "既存SQLiteを削除しました。"
    )

    print(
        f"削除対象: {DB_PATH}"
    )


# =========================================================
# SQLite接続
# =========================================================

conn = sqlite3.connect(
    DB_PATH
)


# =========================================================
# SQLite基本設定
# =========================================================
#
# foreign_keysは今回pandas.to_sqlで作るテーブルに
# FK制約そのものが設定されるわけではないが、
# SQLite利用時の基本設定としてONにしておく。
#
# 実際の参照整合性は、
# このスクリプト後半で明示的に検査する。
# =========================================================

conn.execute(
    "PRAGMA foreign_keys = ON;"
)


# =========================================================
# CSV → SQLite
# =========================================================

loaded_counts = {}


try:

    for table_name, file_name in (
        tables.items()
    ):

        csv_path = (
            RAW_DIR
            / file_name
        )


        # ---------------------------------------------
        # CSV読み込み
        # ---------------------------------------------

        df = pd.read_csv(
            csv_path
        )


        # ---------------------------------------------
        # SQLiteへロード
        # ---------------------------------------------

        df.to_sql(
            table_name,
            conn,
            if_exists="replace",
            index=False,
        )


        loaded_counts[
            table_name
        ] = len(
            df
        )


        print(
            f"{table_name}: "
            f"{len(df):,} rows loaded"
        )


    # =====================================================
    # 修正④ CSV件数とSQLite件数の一致チェック
    # =====================================================
    #
    # 【目的】
    #
    # CSVを読み込めたとしても、
    # SQLite上の件数と一致していることを
    # 明示的に確認する。
    # =====================================================

    print()
    print(
        "【ロード件数確認】"
    )


    for table_name, csv_count in (
        loaded_counts.items()
    ):

        sqlite_count = (
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM "{table_name}"
                """
            )
            .fetchone()[0]
        )


        assert (
            sqlite_count
            ==
            csv_count
        )


        print(
            f"{table_name}: "
            f"CSV={csv_count:,}, "
            f"SQLite={sqlite_count:,} "
            "→ OK"
        )


    # =====================================================
    # 修正⑤ 主キー相当の一意性チェック
    # =====================================================
    #
    # pandas.to_sqlではPRIMARY KEY制約を
    # 自動生成していないため、
    # ID列の一意性をSQLで確認する。
    #
    # これはSQLiteを分析基盤として利用する前の
    # データ品質確認。
    # =====================================================

    unique_key_checks = {
        "clients":
            "client_id",

        "recruiters":
            "recruiter_id",

        "occupations":
            "occupation_id",

        "locations":
            "location_id",

        "candidates":
            "candidate_id",

        "candidate_experiences":
            "candidate_experience_id",

        "candidate_preferences":
            "candidate_preference_id",

        "jobs":
            "job_id",

        "job_entries":
            "entry_id",

        "candidate_activities":
            "activity_id",

        "job_introductions":
            "introduction_id",

        "applications":
            "application_id",

        "workplace_visits":
            "visit_id",

        "placements":
            "placement_id",
    }


    print()
    print(
        "【ID一意性確認】"
    )


    for table_name, id_column in (
        unique_key_checks.items()
    ):

        result = (
            conn.execute(
                f"""
                SELECT
                    COUNT(*) AS row_count,
                    COUNT(DISTINCT "{id_column}")
                        AS distinct_count
                FROM "{table_name}"
                """
            )
            .fetchone()
        )


        row_count = result[0]
        distinct_count = result[1]


        assert (
            row_count
            ==
            distinct_count
        )


        print(
            f"{table_name}.{id_column}: "
            "OK"
        )


    # =====================================================
    # 修正⑥ 外部キー相当の参照整合性チェック
    # =====================================================
    #
    # pandas.to_sqlではFK制約を定義していないため、
    # LEFT JOINを利用して、
    # 親テーブルに存在しないIDがないことを検査する。
    #
    # 戻り値が0件なら正常。
    # =====================================================

    foreign_key_checks = [
        # ---------------------------------------------
        # candidates
        # ---------------------------------------------
        (
            "candidates.ca_id → recruiters.recruiter_id",
            """
            SELECT COUNT(*)
            FROM candidates AS c
            LEFT JOIN recruiters AS r
                ON c.ca_id = r.recruiter_id
            WHERE
                c.ca_id IS NOT NULL
                AND r.recruiter_id IS NULL
            """,
        ),

        # ---------------------------------------------
        # candidate_experiences
        # ---------------------------------------------
        (
            "candidate_experiences.candidate_id → candidates",
            """
            SELECT COUNT(*)
            FROM candidate_experiences AS ce
            LEFT JOIN candidates AS c
                ON ce.candidate_id = c.candidate_id
            WHERE c.candidate_id IS NULL
            """,
        ),

        (
            "candidate_experiences.occupation_id → occupations",
            """
            SELECT COUNT(*)
            FROM candidate_experiences AS ce
            LEFT JOIN occupations AS o
                ON ce.occupation_id = o.occupation_id
            WHERE o.occupation_id IS NULL
            """,
        ),

        # ---------------------------------------------
        # candidate_preferences
        # ---------------------------------------------
        (
            "candidate_preferences.candidate_id → candidates",
            """
            SELECT COUNT(*)
            FROM candidate_preferences AS cp
            LEFT JOIN candidates AS c
                ON cp.candidate_id = c.candidate_id
            WHERE c.candidate_id IS NULL
            """,
        ),

        (
            "candidate_preferences.preferred_occupation_id → occupations",
            """
            SELECT COUNT(*)
            FROM candidate_preferences AS cp
            LEFT JOIN occupations AS o
                ON cp.preferred_occupation_id
                    = o.occupation_id
            WHERE o.occupation_id IS NULL
            """,
        ),

        (
            "candidate_preferences.preferred_location_id → locations",
            """
            SELECT COUNT(*)
            FROM candidate_preferences AS cp
            LEFT JOIN locations AS l
                ON cp.preferred_location_id
                    = l.location_id
            WHERE l.location_id IS NULL
            """,
        ),

        # ---------------------------------------------
        # jobs
        # ---------------------------------------------
        (
            "jobs.client_id → clients",
            """
            SELECT COUNT(*)
            FROM jobs AS j
            LEFT JOIN clients AS c
                ON j.client_id = c.client_id
            WHERE c.client_id IS NULL
            """,
        ),

        (
            "jobs.ra_id → recruiters",
            """
            SELECT COUNT(*)
            FROM jobs AS j
            LEFT JOIN recruiters AS r
                ON j.ra_id = r.recruiter_id
            WHERE r.recruiter_id IS NULL
            """,
        ),

        (
            "jobs.occupation_id → occupations",
            """
            SELECT COUNT(*)
            FROM jobs AS j
            LEFT JOIN occupations AS o
                ON j.occupation_id = o.occupation_id
            WHERE o.occupation_id IS NULL
            """,
        ),

        (
            "jobs.location_id → locations",
            """
            SELECT COUNT(*)
            FROM jobs AS j
            LEFT JOIN locations AS l
                ON j.location_id = l.location_id
            WHERE l.location_id IS NULL
            """,
        ),

        # ---------------------------------------------
        # job_entries
        # ---------------------------------------------
        (
            "job_entries.candidate_id → candidates",
            """
            SELECT COUNT(*)
            FROM job_entries AS je
            LEFT JOIN candidates AS c
                ON je.candidate_id = c.candidate_id
            WHERE c.candidate_id IS NULL
            """,
        ),

        (
            "job_entries.job_id → jobs",
            """
            SELECT COUNT(*)
            FROM job_entries AS je
            LEFT JOIN jobs AS j
                ON je.job_id = j.job_id
            WHERE j.job_id IS NULL
            """,
        ),

        # ---------------------------------------------
        # candidate_activities
        # ---------------------------------------------
        (
            "candidate_activities.candidate_id → candidates",
            """
            SELECT COUNT(*)
            FROM candidate_activities AS ca
            LEFT JOIN candidates AS c
                ON ca.candidate_id = c.candidate_id
            WHERE c.candidate_id IS NULL
            """,
        ),

        (
            "candidate_activities.ca_id → recruiters",
            """
            SELECT COUNT(*)
            FROM candidate_activities AS ca
            LEFT JOIN recruiters AS r
                ON ca.ca_id = r.recruiter_id
            WHERE r.recruiter_id IS NULL
            """,
        ),

        # ---------------------------------------------
        # job_introductions
        # ---------------------------------------------
        (
            "job_introductions.activity_id → candidate_activities",
            """
            SELECT COUNT(*)
            FROM job_introductions AS ji
            LEFT JOIN candidate_activities AS ca
                ON ji.activity_id = ca.activity_id
            WHERE ca.activity_id IS NULL
            """,
        ),

        (
            "job_introductions.job_id → jobs",
            """
            SELECT COUNT(*)
            FROM job_introductions AS ji
            LEFT JOIN jobs AS j
                ON ji.job_id = j.job_id
            WHERE j.job_id IS NULL
            """,
        ),

        # ---------------------------------------------
        # applications
        # ---------------------------------------------
        (
            "applications.job_id → jobs",
            """
            SELECT COUNT(*)
            FROM applications AS a
            LEFT JOIN jobs AS j
                ON a.job_id = j.job_id
            WHERE j.job_id IS NULL
            """,
        ),

        (
            "applications.candidate_id → candidates",
            """
            SELECT COUNT(*)
            FROM applications AS a
            LEFT JOIN candidates AS c
                ON a.candidate_id = c.candidate_id
            WHERE c.candidate_id IS NULL
            """,
        ),

        (
            "applications.ca_id → recruiters",
            """
            SELECT COUNT(*)
            FROM applications AS a
            LEFT JOIN recruiters AS r
                ON a.ca_id = r.recruiter_id
            WHERE r.recruiter_id IS NULL
            """,
        ),

        (
            "applications.source_entry_id → job_entries",
            """
            SELECT COUNT(*)
            FROM applications AS a
            LEFT JOIN job_entries AS je
                ON a.source_entry_id = je.entry_id
            WHERE
                a.source_entry_id IS NOT NULL
                AND je.entry_id IS NULL
            """,
        ),

        (
            "applications.source_introduction_id → job_introductions",
            """
            SELECT COUNT(*)
            FROM applications AS a
            LEFT JOIN job_introductions AS ji
                ON a.source_introduction_id
                    = ji.introduction_id
            WHERE
                a.source_introduction_id IS NOT NULL
                AND ji.introduction_id IS NULL
            """,
        ),

        # ---------------------------------------------
        # workplace_visits
        # ---------------------------------------------
        (
            "workplace_visits.application_id → applications",
            """
            SELECT COUNT(*)
            FROM workplace_visits AS wv
            LEFT JOIN applications AS a
                ON wv.application_id
                    = a.application_id
            WHERE a.application_id IS NULL
            """,
        ),

        # ---------------------------------------------
        # placements
        # ---------------------------------------------
        (
            "placements.application_id → applications",
            """
            SELECT COUNT(*)
            FROM placements AS p
            LEFT JOIN applications AS a
                ON p.application_id
                    = a.application_id
            WHERE a.application_id IS NULL
            """,
        ),
    ]


    print()
    print(
        "【参照整合性確認】"
    )


    for check_name, sql in (
        foreign_key_checks
    ):

        invalid_count = (
            conn.execute(
                sql
            )
            .fetchone()[0]
        )


        assert (
            invalid_count
            ==
            0
        ), (
            f"参照整合性エラー: "
            f"{check_name}, "
            f"{invalid_count}件"
        )


        print(
            f"{check_name}: OK"
        )


    # =====================================================
    # 修正⑦ applications.withdrawal_stage確認
    # =====================================================
    #
    # 今回新しく追加した列が
    # SQLiteに正しくロードされたことを確認する。
    # =====================================================

    application_columns = pd.read_sql_query(
        """
        PRAGMA table_info(applications)
        """,
        conn,
    )


    assert (
        "withdrawal_stage"
        in
        application_columns[
            "name"
        ].tolist()
    )


    print()
    print(
        "【applications追加列確認】"
    )

    print(
        "withdrawal_stage: OK"
    )


    # =====================================================
    # 修正⑧ 分析用INDEX作成
    # =====================================================
    #
    # 【変更前】
    #
    # INDEXを作成していなかった。
    #
    #
    # 【問題点】
    #
    # 今後のSQLマートやEDAでは、
    #
    # candidate_id
    # job_id
    # application_id
    # activity_id
    # 日付
    #
    # を使ったJOIN・GROUP BYが多くなる。
    #
    #
    # 【修正仕様】
    #
    # 分析で頻繁に利用する列へ
    # INDEXを作成する。
    #
    # 数千件規模では速度差は小さいが、
    # データエンジニアリングの設計として
    # 「どのキーで検索・JOINするか」を
    # 明示できる。
    # =====================================================

    index_statements = [
        # candidates
        """
        CREATE INDEX IF NOT EXISTS
            idx_candidates_ca_id
        ON candidates(ca_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_candidates_registration_date
        ON candidates(registration_date)
        """,

        # experiences
        """
        CREATE INDEX IF NOT EXISTS
            idx_candidate_experiences_candidate
        ON candidate_experiences(candidate_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_candidate_experiences_candidate_occupation
        ON candidate_experiences(
            candidate_id,
            occupation_id
        )
        """,

        # preferences
        """
        CREATE INDEX IF NOT EXISTS
            idx_candidate_preferences_candidate_date
        ON candidate_preferences(
            candidate_id,
            effective_from,
            effective_to
        )
        """,

        # jobs
        """
        CREATE INDEX IF NOT EXISTS
            idx_jobs_open_date
        ON jobs(open_date)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_jobs_occupation
        ON jobs(occupation_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_jobs_ra
        ON jobs(ra_id)
        """,

        # job_entries
        """
        CREATE INDEX IF NOT EXISTS
            idx_job_entries_candidate
        ON job_entries(candidate_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_job_entries_job
        ON job_entries(job_id)
        """,

        # activities
        """
        CREATE INDEX IF NOT EXISTS
            idx_candidate_activities_candidate_date
        ON candidate_activities(
            candidate_id,
            activity_date
        )
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_candidate_activities_ca
        ON candidate_activities(ca_id)
        """,

        # introductions
        """
        CREATE INDEX IF NOT EXISTS
            idx_job_introductions_activity
        ON job_introductions(activity_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_job_introductions_job
        ON job_introductions(job_id)
        """,

        # applications
        """
        CREATE INDEX IF NOT EXISTS
            idx_applications_candidate
        ON applications(candidate_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_applications_job
        ON applications(job_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_applications_ca
        ON applications(ca_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_applications_intent_date
        ON applications(intent_confirmed_date)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_applications_status
        ON applications(status)
        """,

        # workplace visits
        """
        CREATE INDEX IF NOT EXISTS
            idx_workplace_visits_application
        ON workplace_visits(application_id)
        """,

        # placements
        """
        CREATE INDEX IF NOT EXISTS
            idx_placements_application
        ON placements(application_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS
            idx_placements_decision_date
        ON placements(decision_date)
        """,
    ]


    for statement in (
        index_statements
    ):

        conn.execute(
            statement
        )


    conn.commit()


    print()
    print(
        "【分析用INDEX作成】"
    )

    print(
        f"{len(index_statements)}個のINDEXを作成しました。"
    )


    # =====================================================
    # 修正⑨ SQLite integrity check
    # =====================================================
    #
    # SQLiteファイル自体に
    # データベース構造上の破損がないことを確認する。
    # =====================================================

    integrity_result = (
        conn.execute(
            "PRAGMA integrity_check;"
        )
        .fetchone()[0]
    )


    assert (
        integrity_result
        ==
        "ok"
    )


    print()
    print(
        "【SQLite integrity check】"
    )

    print(
        integrity_result
    )


    # =====================================================
    # テーブル一覧確認
    # =====================================================

    table_list = pd.read_sql_query(
        """
        SELECT
            name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
        """,
        conn,
    )


    print()
    print(
        "【SQLite内のテーブル一覧】"
    )

    print(
        table_list.to_string(
            index=False
        )
    )


    # =====================================================
    # INDEX一覧確認
    # =====================================================

    index_list = pd.read_sql_query(
        """
        SELECT
            name,
            tbl_name
        FROM sqlite_master
        WHERE type = 'index'
        ORDER BY
            tbl_name,
            name
        """,
        conn,
    )


    print()
    print(
        "【SQLite内のINDEX一覧】"
    )

    print(
        index_list.to_string(
            index=False
        )
    )


finally:

    # =====================================================
    # 接続終了
    # =====================================================

    conn.close()


# =========================================================
# 完了メッセージ
# =========================================================

print()
print(
    "SQLiteデータベースを作成しました。"
)

print(
    f"DB_PATH: {DB_PATH}"
)