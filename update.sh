#!/bin/bash

echo "=========================================="
echo "   星河助手后端 - 更新部署脚本"
echo "=========================================="
echo ""

INSTALL_DIR="/www/wwwroot/xinghe-light"
PORT=8000

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

if [ ! -d "$INSTALL_DIR" ]; then
    error "安装目录不存在: $INSTALL_DIR"
    error "请先运行 deploy_bt.sh 进行首次安装"
    exit 1
fi

cd "$INSTALL_DIR"

info "停止旧服务..."
pkill -f "server.py" 2>/dev/null
sleep 2

if pgrep -f "server.py" > /dev/null; then
    warn "服务仍在运行，强制停止..."
    pkill -9 -f "server.py" 2>/dev/null
    sleep 1
fi

info "拉取最新代码..."
git fetch origin 2>&1
git reset --hard origin/main 2>&1
if [ $? -ne 0 ]; then
    error "拉取失败，请检查网络或Git配置"
    exit 1
fi

info "清理旧配置（重新生成持久化SECRET_KEY）..."
rm -f data/config.json

info "创建数据目录..."
mkdir -p data uploads/apks

info "启动服务..."
nohup $PYTHON server.py > server.log 2>&1 &
echo "服务已启动，PID: $!"

info "等待服务启动..."
sleep 3

if pgrep -f "server.py" > /dev/null; then
    info "服务运行中，检测端口..."
    
    if command -v curl &> /dev/null; then
        sleep 2
        if curl -s "http://127.0.0.1:$PORT/api/health" > /dev/null 2>&1; then
            info "端口 $PORT 正常响应"
        else
            warn "端口检测失败，请检查日志"
        fi
    fi
    
    echo ""
    echo "=========================================="
    echo "   更新成功！"
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
    tail -30 server.log
    exit 1
fi
