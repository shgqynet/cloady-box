# cloady-box

Cloady 上的一台通用小机：debian 根 shell + 一个 HTTP 占位服务（80 端口）+ 4 GiB 持久卷 `/data`。

- 应用由 `docker-compose.yml` 定义，Cloady 读这个文件决定服务、端口和卷。**改端口/加服务就是改这里再推上来**，不用删应用重建。
- 容器根文件系统是临时的，重部署会重来：要装软件请改 `Dockerfile`（`apt-get install`）后推上来，不要只 `apt install`。
- 持久数据放 `/data`：`/data/www` 是静态目录，`/data/logs` 是日志，`/data/start.sh` 存在时开机自动执行（可放自己的常驻服务）。

## 起自己的服务

```sh
cat > /data/start.sh <<'EOF'
#!/bin/sh
# 例：跑个 8080 的 python 服务
cd /data/app && { nohup python3 -m http.server 8080 >> /data/logs/app.log 2>&1 & }
EOF
chmod +x /data/start.sh
```
要让 8080 对外，在 `docker-compose.yml` 的 `ports:` 里加 `"8080"` 再推上来。
