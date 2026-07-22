#!/bin/bash

echo "=========================================="
echo "   星河助手后端 - 零依赖版（宝塔专用）"
echo "=========================================="
echo ""

INSTALL_DIR="/www/wwwroot/xinghe-light"
PORT=8000
REPO_URL="https://github.com/jiabihuan/xinghe-light.git"
GH_ZIP_URL="https://github.com/jiabihuan/xinghe-light/archive/refs/heads/main.zip"
GH_PROXY_ZIP_URL="https://gh-proxy.org/https://github.com/jiabihuan/xinghe-light/archive/refs/heads/main.zip"
REPO_MIRROR="https://gitee.com/jiabihuan/xinghe-light.git"
GITEE_ZIP_URL="https://gitee.com/jiabihuan/xinghe-light/repository/archive/main.zip"
PROXY=""

info() { echo -e "\033[32m[信息]\033[0m $1"; }
error() { echo -e "\033[31m[错误]\033[0m $1"; }
warn() { echo -e "\033[33m[警告]\033[0m $1"; }

find_python() {
    if command -v python3 &> /dev/null; then
        echo $(command -v python3)
        return 0
    fi
    if command -v python &> /dev/null; then
        echo $(command -v python)
        return 0
    fi
    for p in /www/server/pyproject_env/versions/*/bin/python3; do
        if [ -x "$p" ]; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

PYTHON=$(find_python)
if [ -z "$PYTHON" ]; then
    error "未找到Python，请先在宝塔面板安装Python!"
    exit 1
fi
info "检测到Python: $PYTHON"

if [ -d "$INSTALL_DIR" ]; then
    warn "检测到已存在的安装目录"
    read -p "是否删除旧目录重新安装? (y/N): " choice
    if [[ "$choice" == "y" || "$choice" == "Y" ]]; then
        info "停止旧服务..."
        pkill -f "server.py" 2>/dev/null
        pkill -f "xinghe-light" 2>/dev/null
        sleep 1
        info "删除旧目录..."
        rm -rf "$INSTALL_DIR"
    else
        info "保留旧目录，退出安装"
        exit 0
    fi
fi

info "创建安装目录..."
mkdir -p "$(dirname $INSTALL_DIR)"

info "下载代码..."

download_zip() {
    local url=$1
    local tmp_file=$2
    info "尝试下载: $url"
    curl -fsSL "$url" -o "$tmp_file" 2>&1
    return $?
}

TMP_ZIP=$(mktemp /tmp/xinghe_XXXXXX.zip)

download_zip "$GH_ZIP_URL" "$TMP_ZIP"
if [ $? -ne 0 ]; then
    warn "GitHub下载失败，尝试gh-proxy..."
    download_zip "$GH_PROXY_ZIP_URL" "$TMP_ZIP"
    if [ $? -ne 0 ]; then
        warn "gh-proxy失败，尝试Gitee..."
        download_zip "$GITEE_ZIP_URL" "$TMP_ZIP"
        if [ $? -ne 0 ]; then
            error "下载失败，请检查网络"
            rm -f "$TMP_ZIP"
            exit 1
        fi
    fi
fi

info "解压代码..."
rm -rf "$INSTALL_DIR"
unzip -q "$TMP_ZIP" -d "$(dirname $INSTALL_DIR)"
rm -f "$TMP_ZIP"

mv "$(dirname $INSTALL_DIR)/xinghe-light-main" "$INSTALL_DIR" 2>/dev/null || mv "$(dirname $INSTALL_DIR)/xinghe-light" "$INSTALL_DIR" 2>/dev/null

if [ ! -d "$INSTALL_DIR" ]; then
    error "解压失败"
    exit 1
fi

cd "$INSTALL_DIR"

info "零依赖！无需安装任何包"

info "创建数据目录..."
mkdir -p data uploads/apks

info "测试启动..."
timeout 3 $PYTHON -c "
import sys, os
sys.path.insert(0, '.')
import server
print('导入成功，零依赖完美运行!')
" 2>&1

if [ $? -ne 0 ]; then
    error "测试失败"
    exit 1
fi

info "创建启动脚本..."

cat > start.sh << STARTEOF
#!/bin/bash
cd "$(dirname "$0")"
pkill -f "server.py" 2>/dev/null
sleep 1
nohup $PYTHON server.py > server.log 2>&1 &
echo "服务已启动，PID: \$!"
echo "访问: http://你的服务器IP:$PORT"
echo "日志: \$(pwd)/server.log"
STARTEOF
chmod +x start.sh

cat > stop.sh << STOPEOF
#!/bin/bash
pkill -f "server.py"
echo "服务已停止"
STOPEOF
chmod +x stop.sh

cat > restart.sh << RESTARTEOF
#!/bin/bash
cd "$(dirname "$0")"
bash stop.sh
sleep 1
bash start.sh
RESTARTEOF
chmod +x restart.sh

cat > status.sh << STATUSEOF
#!/bin/bash
PID=\$(pgrep -f "server.py" | head -1)
if [ -n "\$PID" ]; then
    echo "服务运行中，PID: \$PID"
    echo "日志文件: \$(dirname "\$0")/server.log"
else
    echo "服务未运行"
fi
STATUSEOF
chmod +x status.sh

info "启动服务..."
bash start.sh
sleep 2

if pgrep -f "server.py" > /dev/null; then
    echo ""
    echo "=========================================="
    echo "   部署成功！零依赖版本"
    echo "=========================================="
    echo ""
    echo "访问地址: http://你的服务器IP:$PORT"
    echo ""
    echo "管理员账号:"
    echo "  用户名: admin"
    echo "  密码: admin123456"
    echo ""
    echo "安装目录: $INSTALL_DIR"
    echo ""
    echo "管理命令:"
    echo "  启动:  cd $INSTALL_DIR && bash start.sh"
    echo "  停止:  cd $INSTALL_DIR && bash stop.sh"
    echo "  重启:  cd $INSTALL_DIR && bash restart.sh"
    echo "  状态:  cd $INSTALL_DIR && bash status.sh"
    echo "  日志:  cd $INSTALL_DIR && tail -f server.log"
    echo ""
    echo "重要提醒: 请尽快修改默认密码！"
    echo "=========================================="
else
    error "服务启动失败"
    echo ""
    echo "日志内容:"
    cat server.log | tail -30
    exit 1
fi
