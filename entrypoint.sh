#!/bin/sh
set -e

mkdir -p /data/www /data/logs

if [ ! -f /data/www/index.html ]; then
  cat > /data/www/index.html <<'HTML'
<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>cloady box</title>
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:60px auto;padding:0 16px;color:#222}
h1{font-size:22px}code{background:#f2f2f2;padding:2px 6px;border-radius:4px}</style></head>
<body><h1>cloady box 运行中</h1>
<p>这是一个通用容器。持久目录：<code>/data</code>（www 静态目录、logs、start.sh 启动钩子）。</p>
<p>放 <code>/data/start.sh</code> 即可随容器启动跑自己的服务。</p>
</body></html>
HTML
fi

python3 -m http.server 80 --directory /data/www >> /data/logs/http.log 2>&1 &

if [ -f /data/start.sh ]; then
  sh /data/start.sh >> /data/logs/start.log 2>&1 &
fi

wait
