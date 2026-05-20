# gourmai

居酒屋・飲食店検索/レビュー用の Django + Vite アプリケーション。

## 概要
- バックエンド: Django REST Framework
- フロントエンド: Vite + Vanilla JS (SPA、PWA 対応)
- 外部 API: HotPepper / Google Places (Maps) / Google Gemini
- DB: 本番は PostgreSQL (Neon)、ローカルは sqlite

主な機能: 店舗検索 (位置・キーワード / 自然言語 / AI レコメンド)、お気に入り、来店記録、評価、コメント、検索履歴、人気店ランキング、PWA、利用規約 / プライバシーポリシー。

## セットアップ (ローカル開発)
1. リポジトリをクローン
   ```bash
   git clone <repo-url>
   cd gourmai
   ```
2. Python 仮想環境を作成・有効化
   ```bash
   python -m venv backend/.venv
   source backend/.venv/bin/activate   # Linux / macOS
   ```
3. 依存パッケージをインストール
   ```bash
   pip install -r backend/requirements.txt
   cd frontend && npm install
   ```
4. `.env` を作成して必要な環境変数を設定
   ```bash
   cp .env.example .env
   ```
5. マイグレーション・静的ファイル
   ```bash
   cd backend
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```
6. サーバー起動
   ```bash
   # フロントエンド開発
   cd frontend && npm run dev
   # バックエンド単体
   cd backend && python manage.py runserver
   ```

## 環境変数

| 名前 | 必須 | 説明 |
| --- | --- | --- |
| `SECRET_KEY` | 本番では必須 | Django の SECRET_KEY |
| `DEBUG` | | "true" で開発モード |
| `DATABASE_URL` | 本番では必須 | `postgres://user:pass@host:port/dbname` |
| `ALLOWED_HOSTS` | | カンマ区切りで本番ドメインを指定 |
| `CORS_ALLOWED_ORIGINS` | | カンマ区切りで本番フロントドメイン |
| `HOTPEPPER_API_KEY` | | HotPepper Webservice |
| `GOOGLE_MAPS_API_KEY` | | Google Places (New) |
| `GEMINI_API_KEY` | | Gemini (Generative Language) |
| `RATELIMIT_ENABLE` | | "false" でレート制限を無効化 (テスト用) |
| `NG_WORDS` | | カンマ区切り。コメント投稿の NG ワード |
| `COMMENT_MAX_LENGTH` | | コメント最大文字数 (default: 1000) |
| `LOG_LEVEL` | | "DEBUG" / "INFO" / "WARNING" |

## デプロイ (Render など)
1. Web Service を作成、Docker を選択
2. 環境変数を設定 (上表参照)
3. 初回のみ `python manage.py migrate` と `collectstatic --noinput` を実行
4. cron として `python manage.py cleanup_old_data` を 1日1回 (Render Cron Job 等)

## 運用コマンド

```bash
# 古い検索履歴 / 店舗表示履歴 / 通報レコードの削除
python manage.py cleanup_old_data

# ドライラン
python manage.py cleanup_old_data --dry-run
```

## 主なエンドポイント

| パス | 用途 |
| --- | --- |
| `GET  /api/restaurants/healthz/` | liveness |
| `GET  /api/restaurants/readyz/` | readiness (DB + cache) |
| `GET  /api/restaurants/search/` | 店舗検索 |
| `POST /api/restaurants/natural-search/` | Gemini で自然言語検索 |
| `GET  /api/restaurants/recommendations/` | レコメンド |
| `POST /api/restaurants/auth/register/` | 登録 (利用規約同意必須) |
| `POST /api/restaurants/auth/login/` | ログイン |
| `DELETE /api/restaurants/auth/delete/` | 退会 |
| `GET/POST /api/restaurants/comments/<shop_id>/` | コメント |
| `POST /api/restaurants/comments/<id>/report/` | コメント通報 |
| `GET  /api/restaurants/admin/stats/` | 管理者統計 |

## セキュリティとモデレーション
- 本番では HTTPS 強制 / HSTS / SecureCookie / SSL リダイレクト
- ログイン・登録・検索・コメント投稿にレート制限 (django-ratelimit)
- ログイン失敗メッセージはユーザー列挙されないよう統一
- コメントは NG ワード / スパムヒューリスティック / IP・UA 記録 / 通報 (3 件で自動非表示)
- 退会 API はアカウントと関連レコードをすべて削除

## ライセンス
[MIT ライセンス](LICENSE) の下で公開しています。
