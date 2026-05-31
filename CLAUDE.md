# travel-roulette プロジェクト引継ぎドキュメント

## 「再起動したい」と言われたら

このファイルを最新の状態に書き直し、memory/ のプロジェクトメモリも更新すること。
更新後に「引継ぎ完了です。次のセッションでもこの状態から再開できます。」と報告する。

---

## プロジェクト概要

| 項目 | 内容 |
|---|---|
| サービス名 | 旅行プラン ルーレット |
| URL | https://travel-roulette-justeco.com |
| 目的 | 全国47都道府県のスポットをランダム提案。Google AdSense収益化が目標 |
| 運営者 | Justeco（2026.justeco@gmail.com） |

---

## 技術スタック

| 項目 | 内容 |
|---|---|
| バックエンド | Python 3.11 / Flask 3.x / gunicorn |
| データベース | Supabase（PostgreSQL、無料枠） |
| ホスティング | Render（無料枠、GitHub連携で自動デプロイ） |
| スリープ防止 | UptimeRobot |
| ドメイン | Xserver（DNSのみ、ホスティングはRender） |
| リポジトリ | https://github.com/2026justeco-crypto/travel-roulette （main ブランチ） |
| ローカルパス | C:\dev\team\shared-app\travel-roulette |

---

## 環境変数（Render に設定済み / ローカルは .env）

```
SUPABASE_URL=https://qthcesthighfwkjvleoy.supabase.co
SUPABASE_SERVICE_KEY=（secret、GitHubに上げない）
ADMIN_SECRET=hungaa4649
```

---

## Supabase スキーマ

### spots テーブル
```
id SERIAL PK / name TEXT / pref TEXT / region TEXT
category TEXT[] / seasons TEXT[] / description TEXT
highlights TEXT[] / links JSONB / nearby TEXT[]
rainy_alternatives JSONB
```
- 150スポット登録済み
- RLS有効・public SELECT 許可

### posts テーブル（旅の声）
```
id BIGSERIAL PK / spot_id INT FK / content TEXT（100文字以内）
created_at TIMESTAMPTZ / ip_hash TEXT / photo_url TEXT（nullable）
```
- 1日5件/IPのレート制限
- 投稿後10分以内なら本人削除可（HMAC トークン方式）

### suggestions テーブル（スポット提案）
```
id BIGSERIAL PK / spot_name TEXT / near_spot TEXT
description TEXT / created_at TIMESTAMPTZ
```

### Storage
- バケット: `post-photos`（public）
- 投稿写真を保存（jpg/png/webp・5MB以内）

---

## 主要ファイル

| ファイル | 役割 |
|---|---|
| `app.py` | Flaskアプリ本体。Supabaseクライアント・全ルート定義 |
| `data.py` | 旧スポットデータ（移行済み、参照のみ） |
| `migrate.py` | 初回移行スクリプト（実行済み、再利用不要） |
| `schema.sql` | Supabaseテーブル定義SQL |
| `templates/spot_detail.html` | スポット詳細ページ（旅の声・提案フォーム含む） |
| `templates/admin_spot_new.html` | スポット追加管理画面 |
| `static/style.css` | 全スタイル（CSS変数: --color-main #2c5f2e） |
| `.env` | ローカル環境変数（gitignore済み） |

---

## 実装済み機能

- [x] ランダムルーレット（地方・カテゴリ・季節フィルター付き）
- [x] スポット詳細ページ（150件、SEO対応）
- [x] 地方別・都道府県別・カテゴリ別一覧ページ
- [x] 旅の声（匿名投稿・写真添付・10分以内削除）
- [x] スポット提案フォーム（折りたたみ式）
- [x] スポット追加管理画面（/admin/spots/new?secret=...）
- [x] キャッシュリフレッシュ（/admin/refresh-spots?secret=...）
- [x] ads.txt（AdSense publisher ID設定済み）
- [x] About / プライバシーポリシー ページ
- [x] 壊れたリンク36件を正しいURLに修正済み

---

## 管理用URL

| 用途 | URL |
|---|---|
| スポット追加 | https://travel-roulette-justeco.com/admin/spots/new?secret=hungaa4649 |
| キャッシュ更新 | https://travel-roulette-justeco.com/admin/refresh-spots?secret=hungaa4649 |

---

## 開発ワークフロー

```powershell
# ローカル起動
cd C:\dev\team\shared-app\travel-roulette
python app.py

# デプロイ（push で Render が自動デプロイ）
git add <files>
git commit -m "説明"
git push origin main

# Supabase のデータ変更後にキャッシュ更新
# ブラウザで /admin/refresh-spots?secret=hungaa4649 にアクセス
```

---

## 現在の課題 / 次のステップ

- [ ] AdSense 再申請（旅の声に実投稿が20〜30件貯まったら）
- [ ] 旅の声の投稿を増やす（友人・家族に依頼）
- [ ] 人気スポットの説明文を手書きで補強（テンプレ脱却）
- [ ] 編集コンテンツページの追加（「春のおすすめ旅行先5選」など）
- [ ] 写真添付機能の本番テスト

---

## 注意事項

- `requirements.txt` は UTF-8 で保存すること（UTF-16 だと pip が読めない）
- Windows の PowerShell では `cat >> file` の代わりに Bash ツールを使う
- Supabase の `description` カラムは Python 側では `desc` にマッピングして使用
- スポットキャッシュは起動時に Supabase から全件取得（インメモリキャッシュ方式）
