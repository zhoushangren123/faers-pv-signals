#!/usr/bin/env bash
# ============================================================
#  FAERS 仓库一键发布到 GitHub (macOS / Linux)
#  用法:
#    ./setup_github.sh                              # 交互式输入仓库 URL
#    ./setup_github.sh https://github.com/用户/仓库.git   # 直接带 URL
#  说明: 已有 .git 时幂等；会检测并提示配置 git user.name/email；
#        自动设置 main 分支、remote origin，并首次 push。
# ============================================================
set -e
cd "$(dirname "$0")"

echo "[FAERS] 初始化 Git 仓库并推送到 GitHub ..."
if ! command -v git >/dev/null 2>&1; then
    echo "[错误] 未检测到 git，请先安装 Git (https://git-scm.com) 并加入 PATH"
    exit 1
fi

# 1) 初始化（幂等）
if [ ! -d .git ]; then
    git init
    echo "[FAERS] 已 git init"
else
    echo "[FAERS] 已是 git 仓库，跳过 init"
fi

# 2) 配置 user（若缺失则交互）
if [ -z "$(git config user.name)" ] || [ -z "$(git config user.email)" ]; then
    echo "[提示] 检测到尚未配置 git user.name / user.email（首次需填写，只问一次）"
    read -p "请输入 git user.name: " GNAME
    read -p "请输入 git user.email: " GEMAIL
    git config user.name "$GNAME"
    git config user.email "$GEMAIL"
fi

# 3) 读取远程 URL（参数或交互）
REMOTE_URL="$1"
if [ -z "$REMOTE_URL" ]; then
    read -p "请输入 GitHub 仓库 URL (https://github.com/用户名/仓库.git): " REMOTE_URL
fi
if [ -z "$REMOTE_URL" ]; then
    echo "[错误] 未提供仓库 URL，已取消"
    exit 1
fi

# 4) 分支 + remote
git branch -M main
if git remote get-url origin >/dev/null 2>&1; then
    echo "[FAERS] remote origin 已存在，更新为 $REMOTE_URL"
    git remote set-url origin "$REMOTE_URL"
else
    git remote add origin "$REMOTE_URL"
fi

# 5) 暂存 + 提交（无改动则跳过）
git add .
if git diff --cached --quiet; then
    echo "[FAERS] 没有需要提交的改动"
else
    git commit -m "init: FAERS PV signal detection pipeline"
fi

# 6) 推送
echo "[FAERS] 推送到 origin/main ..."
git push -u origin main
echo "[完成] 仓库已推送。GitHub 页面: ${REMOTE_URL%.git}"
