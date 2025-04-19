-- @file: schema.sql
-- @desc: アットコスメ動画生成システムのデータベーススキーマ

-- 製品マスターテーブル
CREATE TABLE IF NOT EXISTS products (
  product_id    TEXT PRIMARY KEY,  -- アットコスメ製品ID
  genre         TEXT,              -- ジャンル(化粧水、乳液など)
  channel       TEXT,              -- チャンネル(スーパー、ドラッグストアなど)
  name          TEXT,              -- 製品名
  brand         TEXT,              -- ブランド名
  image_url     TEXT,              -- 製品画像URL
  scraped_rank  INTEGER,           -- スクレイピング時の順位
  first_seen    DATETIME,          -- 最初に見つけた日時
  last_used     DATETIME           -- 最後に使用した日時
);

-- 実行履歴テーブル
CREATE TABLE IF NOT EXISTS runs (
  run_id        INTEGER PRIMARY KEY AUTOINCREMENT,  -- 実行ID
  genre         TEXT,                               -- 対象ジャンル
  channel       TEXT,                               -- 対象チャンネル
  created_at    DATETIME,                           -- 作成日時
  status        TEXT,                               -- ステータス(started/success/error)
  video_gs_uri  TEXT,                               -- Cloud StorageのURI
  error_details TEXT                                -- エラー詳細(エラー時)
);

-- レビューキャッシュテーブル
CREATE TABLE IF NOT EXISTS review_cache (
  product_id    TEXT PRIMARY KEY,  -- アットコスメ製品ID
  summary1      TEXT,              -- 要約1
  summary2      TEXT,              -- 要約2
  summary3      TEXT,              -- 要約3
  updated_at    DATETIME           -- 更新日時
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_products_genre ON products(genre);
CREATE INDEX IF NOT EXISTS idx_products_channel ON products(channel);
CREATE INDEX IF NOT EXISTS idx_products_last_used ON products(last_used);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);