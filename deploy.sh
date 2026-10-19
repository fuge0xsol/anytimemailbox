#!/usr/bin/env bash
# 双平台部署:GitHub Pages + Cloudflare Pages
# 用前:gh auth switch 到目标账号;wrangler 已登录
set -e
cd "$(dirname "$0")"

python scripts/04_build_site.py   # 确保最新

MSG="deploy: refresh data $(date +%F)"

# 1) GitHub Pages(仓库: <user>/residential-mailbox,Pages 指向 main /docs 或 gh-pages)
if [ ! -d .git ]; then
  git init && git branch -m main
  git remote add origin git@github.com:fuge0xsol/residential-mailbox.git
fi
mkdir -p docs && cp dist/index.html docs/
git add -A && git commit -m "$MSG" || true
git push -u origin main
echo "GitHub Pages: 确认仓库 Settings→Pages 指向 main /(root) 或 /docs"

# 2) Cloudflare Pages(直接上传 dist,项目名自定)
npx wrangler pages deploy dist --project-name residential-mailbox --commit-dirty=true
echo "Done. CF: https://residential-mailbox.pages.dev"
