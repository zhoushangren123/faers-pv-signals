#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAERS 药物警戒工具箱 · 启动器
=============================
游戏启动器风格的主入口：在一个界面里管理并启动全部工具，
无需记忆命令、无需手动开黑窗口。

工具：
  💊 FAERS 本地信号检测（离线）  端口 8502
  🌐 FAERS 在线检测（openFDA）   端口 8501

运行：
  python launcher.py
  或直接双击 启动器.bat
"""

import os
import socket
import subprocess
import sys
import time

import streamlit as st

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PYEXE = os.path.join(APP_DIR, "python", "python.exe")
if not os.path.exists(PYEXE):
    PYEXE = sys.executable

LOG_DIR = os.path.join(APP_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LAUNCHER_PORT = 8500

TOOLS = [
    {
        "key": "local",
        "icon": "💊",
        "name": "FAERS 本地信号检测",
        "tag": "离线 · 推荐",
        "desc": "读取本机 FAERS/AERS 季度原始数据，对指定药品做 ROR / PRR / BCPNN "
                "不成比例分析，输出 Top 异常不良反应榜。全程零联网，数据最全。",
        "file": "faers_local_app.py",
        "port": 8502,
        "accent": "#22d3ee",
    },
    {
        "key": "online",
        "icon": "🌐",
        "name": "FAERS 在线检测",
        "tag": "需联网",
        "desc": "通过 FDA openFDA API 实时查询。适合临时快速验证单一药品，"
                "但受公司网络影响，且数据完整度不如本地版。",
        "file": "streamlit_faers_app.py",
        "port": 8501,
        "accent": "#a78bfa",
    },
]


# ---------------------------------------------------------------- 进程管理
def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def launch(tool: dict) -> tuple:
    """后台启动某个工具的 Streamlit 服务。返回 (ok, message)。"""
    if port_open(tool["port"]):
        return True, "已在运行"
    log_path = os.path.join(LOG_DIR, f"{tool['key']}.log")
    try:
        log = open(log_path, "w", encoding="utf-8", errors="ignore")
        creation = 0
        if os.name == "nt":
            creation = (subprocess.DETACHED_PROCESS
                        | subprocess.CREATE_NEW_PROCESS_GROUP)
        subprocess.Popen(
            [PYEXE, "-m", "streamlit", "run", tool["file"],
             "--server.port", str(tool["port"]),
             "--server.headless", "true",
             "--browser.gatherUsageStats", "false"],
            cwd=APP_DIR, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, creationflags=creation,
        )
    except Exception as e:
        return False, f"启动失败：{e}"

    for _ in range(60):          # 最多等 30 秒
        time.sleep(0.5)
        if port_open(tool["port"]):
            return True, "启动成功"
    return False, "启动超时，请查看 logs 目录"


def stop(tool: dict) -> tuple:
    """按端口找到监听进程并结束（含子进程）。"""
    port = tool["port"]
    try:
        # 中文 Windows 的 netstat 输出是 GBK 编码，必须用 latin-1 兜底解码；
        # 若按默认 utf-8 解码会抛 UnicodeDecodeError，导致「停止」按钮失效。
        raw = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, timeout=15).stdout
        out = raw.decode("latin-1", errors="ignore")
    except Exception as e:
        return False, f"查询端口失败：{e}"

    pids = set()
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts:
                pids.add(parts[-1])

    if not pids:
        return True, "未在运行"

    ok = True
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"],
                           capture_output=True, timeout=15)
        except Exception:
            ok = False
    time.sleep(1.0)
    return (not port_open(port)), "已停止" if ok else "停止时出现问题"


# ---------------------------------------------------------------- 页面样式
CSS = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
[data-testid="stToolbar"] {display: none;}
[data-testid="stDecoration"] {display: none;}

.stApp {
  background:
    radial-gradient(1200px 600px at 15% -10%, #1e3a8a55 0%, transparent 60%),
    radial-gradient(900px 500px at 90% 0%, #0e749055 0%, transparent 55%),
    linear-gradient(180deg, #0b1220 0%, #0f172a 100%);
  background-attachment: fixed;
}
.block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1180px;}

/* 顶部横幅 */
.hero {
  padding: 30px 34px; border-radius: 20px; margin-bottom: 22px;
  background: linear-gradient(120deg, #0f766e 0%, #1d4ed8 55%, #6d28d9 100%);
  box-shadow: 0 18px 40px rgba(2,6,23,.55);
  position: relative; overflow: hidden;
}
.hero::after{
  content:""; position:absolute; inset:0;
  background: radial-gradient(500px 200px at 85% 20%, rgba(255,255,255,.22), transparent 70%);
}
.hero h1 {color:#fff; font-size:30px; margin:0 0 6px 0; letter-spacing:.5px;}
.hero p  {color:#dbeafe; margin:0; font-size:14px; opacity:.95;}
.hero .ver{
  position:absolute; right:22px; top:20px; color:#e0f2fe;
  font-size:12px; background:rgba(255,255,255,.16);
  padding:4px 12px; border-radius:999px; border:1px solid rgba(255,255,255,.25);
}

/* 工具卡片 */
.card{
  background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.025));
  border: 1px solid rgba(255,255,255,.10);
  border-radius: 18px; padding: 22px 22px 16px 22px;
  height: 100%; transition: .22s;
  box-shadow: 0 8px 24px rgba(2,6,23,.35);
}
.card:hover{ transform: translateY(-3px); border-color: rgba(255,255,255,.22);
  box-shadow: 0 16px 36px rgba(2,6,23,.5); }
.card .icon{ font-size: 34px; line-height:1; margin-bottom: 10px; }
.card .name{ color:#f8fafc; font-size:19px; font-weight:700; margin-bottom:4px; }
.card .tag{
  display:inline-block; font-size:11px; padding:2px 9px; border-radius:999px;
  background: rgba(34,211,238,.16); color:#67e8f9; border:1px solid rgba(34,211,238,.3);
  margin-bottom: 10px;
}
.card .desc{ color:#94a3b8; font-size:13px; line-height:1.65; min-height: 66px; }
.card .meta{ color:#64748b; font-size:12px; margin-top:8px;
  border-top:1px dashed rgba(255,255,255,.10); padding-top:8px; }

/* 状态条 */
.statusbar{
  margin-top: 18px; padding: 12px 18px; border-radius: 14px;
  background: rgba(255,255,255,.04); border:1px solid rgba(255,255,255,.08);
  color:#94a3b8; font-size:12.5px; display:flex; gap: 22px; flex-wrap: wrap;
}
.statusbar b{ color:#cbd5e1; font-weight:600; }

.badge-run{ color:#4ade80; font-weight:700; }
.badge-idle{ color:#64748b; }

.stButton > button{
  border-radius: 12px; font-weight: 600; border:1px solid rgba(255,255,255,.14);
  background: rgba(255,255,255,.06); color:#e2e8f0;
}
.stButton > button:hover{ background: rgba(255,255,255,.13); color:#fff; }
.stButton > button[kind="primary"]{
  background: linear-gradient(120deg,#0891b2,#2563eb); border:none; color:#fff;
}
.stButton > button[kind="primary"]:hover{
  background: linear-gradient(120deg,#06b6d4,#3b82f6);
}
.sect-title{ color:#e2e8f0; font-size:15px; font-weight:700; margin: 22px 0 10px 0; }
</style>
"""


def main():
    st.set_page_config(page_title="FAERS 药物警戒工具箱",
                       page_icon="💊", layout="wide",
                       initial_sidebar_state="collapsed")
    st.markdown(CSS, unsafe_allow_html=True)

    # ---------------- 顶部横幅 ----------------
    st.markdown(
        """
        <div class="hero">
          <div class="ver">v1.0 · 离线工具箱</div>
          <h1>💊 FAERS 药物警戒工具箱</h1>
          <p>一键启动 · 无需命令行 · 无需联网（本地检测）｜ROR / PRR / BCPNN 不成比例分析</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------------- 工具卡片 ----------------
    st.markdown('<div class="sect-title">应用</div>', unsafe_allow_html=True)
    cols = st.columns(len(TOOLS), gap="large")

    for col, tool in zip(cols, TOOLS):
        with col:
            running = port_open(tool["port"])
            badge = ('<span class="badge-run">● 运行中</span>'
                     if running else '<span class="badge-idle">○ 未启动</span>')
            st.markdown(
                f"""
                <div class="card">
                  <div class="icon">{tool['icon']}</div>
                  <div class="name">{tool['name']}</div>
                  <div class="tag">{tool['tag']}</div>
                  <div class="desc">{tool['desc']}</div>
                  <div class="meta">本地端口 <b>{tool['port']}</b>　·　状态 {badge}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if running:
                b1, b2 = st.columns(2)
                with b1:
                    st.link_button("🌐 打开",
                                   f"http://localhost:{tool['port']}",
                                   use_container_width=True)
                with b2:
                    if st.button("■ 停止", key=f"stop_{tool['key']}",
                                 use_container_width=True):
                        ok, msg = stop(tool)
                        (st.success if ok else st.warning)(msg)
                        st.rerun()
            else:
                if st.button(f"▶ 启动 {tool['name']}",
                             key=f"run_{tool['key']}",
                             type="primary", use_container_width=True):
                    with st.spinner(f"正在启动 {tool['name']}…"):
                        ok, msg = launch(tool)
                    if ok:
                        st.success(f"{msg}　→　http://localhost:{tool['port']}")
                        st.rerun()
                    else:
                        st.error(msg)

    # ---------------- 数据目录 ----------------
    st.markdown('<div class="sect-title">数据目录</div>', unsafe_allow_html=True)
    dc1, dc2 = st.columns([3, 1])
    with dc1:
        st.caption(
            "本地检测需要 FAERS/AERS 季度原始数据（形如 "
            "`faers_ascii_2018Q1.zip` 的文件）。"
            "在应用内点「🔍 自动查找」可扫描全盘，也可直接粘贴文件夹路径。"
        )
    with dc2:
        if st.button("🔍 扫描本机数据目录", use_container_width=True):
            with st.spinner("扫描 C~J 盘…"):
                try:
                    sys.path.insert(0, APP_DIR)
                    import faers_local_signals as fls
                    cands = fls.scan_candidate_dirs()
                except Exception as e:
                    cands = []
                    st.error(f"扫描失败：{e}")
                st.session_state["cands"] = cands

    cands = st.session_state.get("cands")
    if cands:
        for p, n, a, b in cands:
            st.success(f"📁 `{p}`　—　{n} 个季度（{a} ~ {b}）")
    elif cands == []:
        st.info("未扫描到数据目录，可在应用内手动填写路径。")

    # ---------------- 文档 ----------------
    st.markdown('<div class="sect-title">文档</div>', unsafe_allow_html=True)
    d1, d2, d3 = st.columns(3)
    with d1:
        st.caption("**README.md**　项目说明与快速开始")
    with d2:
        st.caption("**CHECKLIST.md**　首次运行检查清单")
    with d3:
        st.caption("**docs/**　业务说明.html、操作 SOP.html")
    st.caption(f"文档目录：`{os.path.join(APP_DIR, 'docs')}`")

    # ---------------- 底部状态条 ----------------
    try:
        pyv = subprocess.run([PYEXE, "--version"], capture_output=True,
                             text=True, timeout=15).stdout.strip()
    except Exception:
        pyv = "未知"
    runtime = "内置绿色版" if PYEXE != sys.executable else "系统 Python"

    st.markdown(
        f"""
        <div class="statusbar">
          <span>运行环境：<b>{runtime}</b></span>
          <span>{pyv}</span>
          <span>启动器端口：<b>{LAUNCHER_PORT}</b></span>
          <span>工具箱目录：<b>{APP_DIR}</b></span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(
        "提示：关闭本页面不会停止已启动的工具；如需退出，请先在卡片上点「■ 停止」，"
        "或直接关闭运行 启动器.bat 的那个黑窗口。"
    )


if __name__ == "__main__":
    main()
