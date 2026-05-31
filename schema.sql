-- =========================================
-- travel-roulette Supabase スキーマ
-- Supabase SQL Editor に貼り付けて実行する
-- =========================================

-- spots テーブル（スポットマスタ）
CREATE TABLE spots (
  id                 SERIAL       PRIMARY KEY,
  name               TEXT         NOT NULL,
  pref               TEXT         NOT NULL,
  region             TEXT         NOT NULL,
  category           TEXT[]       NOT NULL DEFAULT '{}',
  seasons            TEXT[]       NOT NULL DEFAULT '{}',
  description        TEXT         NOT NULL DEFAULT '',
  highlights         TEXT[]       NOT NULL DEFAULT '{}',
  links              JSONB        NOT NULL DEFAULT '[]',
  nearby             TEXT[]       NOT NULL DEFAULT '{}',
  rainy_alternatives JSONB        NOT NULL DEFAULT '[]'
);

-- posts テーブル（旅の声）
CREATE TABLE posts (
  id         BIGSERIAL    PRIMARY KEY,
  spot_id    INT          NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
  content    TEXT         NOT NULL CHECK (char_length(content) <= 100),
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  ip_hash    TEXT         NOT NULL
);

CREATE INDEX posts_spot_id_idx ON posts(spot_id);
CREATE INDEX posts_ip_created_idx ON posts(ip_hash, created_at);

-- suggestions テーブル（スポット提案）
CREATE TABLE suggestions (
  id          BIGSERIAL    PRIMARY KEY,
  spot_name   TEXT         NOT NULL,
  near_spot   TEXT         NOT NULL,
  description TEXT         NOT NULL,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- =========================================
-- Row Level Security (RLS) ポリシー
-- =========================================

ALTER TABLE spots       ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts       ENABLE ROW LEVEL SECURITY;
ALTER TABLE suggestions ENABLE ROW LEVEL SECURITY;

-- spots: 全員が読み取り可（書き込みは service_role のみ）
CREATE POLICY "spots_select_public"
  ON spots FOR SELECT USING (true);

-- posts: 全員が読み取り・投稿可
CREATE POLICY "posts_select_public"
  ON posts FOR SELECT USING (true);
CREATE POLICY "posts_insert_public"
  ON posts FOR INSERT WITH CHECK (true);

-- suggestions: 投稿のみ可（読み取りはダッシュボードで管理者のみ）
CREATE POLICY "suggestions_insert_public"
  ON suggestions FOR INSERT WITH CHECK (true);
