@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM  FAERS 仓库一键发布到 GitHub (Windows)
REM  用法:
REM    run  setup_github.bat                            (交互式输入仓库 URL)
REM    or   setup_github.bat https://github.com/用户/仓库.git
REM  说明: 已有 .git 时幂等；会检测并提示配置 git user.name/email；
REM        自动设置 main 分支、remote origin，并首次 push。
REM ============================================================
cd /d "%~dp0"

echo [FAERS] 初始化 Git 仓库并推送到 GitHub ...
where git >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 git，请先安装 Git (https://git-scm.com) 并加入 PATH
    pause
    exit /b 1
)

REM 1) 初始化（幂等）
if not exist ".git" (
    git init
    echo [FAERS] 已 git init
) else (
    echo [FAERS] 已是 git 仓库，跳过 init
)

REM 2) 配置 user（若缺失则交互）
for /f "tokens=*" %%i in ('git config user.name') do set _name=%%i
if not defined _name (
    set /p GNAME=请输入 git user.name: 
    set /p GEMAIL=请输入 git user.email: 
    git config user.name "%GNAME%"
    git config user.email "%GEMAIL%"
)

REM 3) 读取远程 URL（参数或交互）
set "REMOTE_URL=%~1"
if "%REMOTE_URL%"=="" (
    set /p REMOTE_URL=请输入 GitHub 仓库 URL (https://github.com/用户名/仓库.git): 
)
if "%REMOTE_URL%"=="" (
    echo [错误] 未提供仓库 URL，已取消
    pause
    exit /b 1
)

REM 4) 分支 + remote
git branch -M main
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    git remote add origin %REMOTE_URL%
) else (
    echo [FAERS] remote origin 已存在，更新
    git remote set-url origin %REMOTE_URL%
)

REM 5) 暂存 + 提交（无改动则跳过）
git add .
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "init: FAERS PV signal detection pipeline"
) else (
    echo [FAERS] 没有需要提交的改动
)

REM 6) 推送
echo [FAERS] 推送到 origin/main ...
git push -u origin main
echo [完成] 仓库已推送。GitHub 页面: %REMOTE_URL%
pause
