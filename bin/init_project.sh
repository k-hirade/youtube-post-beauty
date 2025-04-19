#!/usr/bin/env bash
#
# init_project.sh
# ───────────────
# youtube-post-beauty ディレクトリ直下に
# プロジェクト骨組みを作成するワンショットスクリプト
#

set -euo pipefail

# 1) ルートを取得（bin/ の一つ上）
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

echo "Creating project skeleton under: $ROOT_DIR"

# 2) ディレクトリ群
declare -a DIRS=(
  "bin"
  "config"
  "data/temp"
  "data/output"
  "data/logs"
  "src"
  "src/scheduler"
  "src/scraper"
  "src/selector"
  "src/db"
  "src/review"
  "src/assets"
  "src/video"
  "src/uploader"
  "src/qa"
  "src/notifier"
  "src/util"
  "tests"
)

for d in "${DIRS[@]}"; do
  mkdir -p "${ROOT_DIR}/${d}"
done

# 3) 空の __init__.py と主要プレースホルダ
touch "${ROOT_DIR}/src/__init__.py"
for pkg in scheduler scraper selector db review assets video uploader qa notifier util; do
  touch "${ROOT_DIR}/src/${pkg}/__init__.py"
done
touch "${ROOT_DIR}/src/main.py"
touch "${ROOT_DIR}/src/db/schema.sql"
touch "${ROOT_DIR}/requirements.txt"
touch "${ROOT_DIR}/README.md"
touch "${ROOT_DIR}/.gitignore"

# 4) config テンプレート
if [[ ! -f "${ROOT_DIR}/config/.env.example" ]]; then
  cat > "${ROOT_DIR}/config/.env.example" <<'EOF'
# OpenAI
OPENAI_API_KEY=

# Google Cloud
GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
GCP_PROJECT_ID=
GCS_BUCKET=cosme-shorts

# Slack
SLACK_WEBHOOK_URL=
EOF
fi

echo "✅ Project skeleton created successfully"

