#!/bin/sh
# cloady box 入口：状态面板服务（80 端口）+ 可选自定义启动钩子
set -e

mkdir -p /data/www /data/logs

if [ ! -f /data/www/index.html ]; then
  cat > /data/www/index.html <<'HTML'
<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>cloady box</title>
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:60px auto;padding:0 16px;color:#222}</style>
</head><body>
<h1>cloady box 运行中</h1>
<p>持久目录：<code>/data</code>（www 静态目录、logs、start.sh 启动钩子、panel.env 面板配置）。</p>
</body></html>
HTML
fi

# 状态面板服务（内部带重启循环）
( while true; do
    python3 /usr/local/bin/server.py || true
    echo "$(date '+%F %T') server.py exited, restarting" >> /data/logs/panel.log
    sleep 2
  done ) &

# 自定义开机钩子（独立运行，不影响面板）
if [ -f /data/start.sh ]; then
  sh /data/start.sh >> /data/logs/start.log 2>&1 &
fi

wait
