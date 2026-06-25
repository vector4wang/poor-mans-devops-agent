#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Poor Man's DevOps Agent - 乞丐版运维助手
Poor Man's DevOps Agent - A lightweight production debugging assistant

支持 Python 3.6+

使用方法:
    # 方式一：命令行参数
    python agent.py --api-url https://your-api-url/v1/chat/completions --api-key your-api-key --model gpt-4o

    # 方式二：设置环境变量
    export DEBUGBOT_API_URL="https://your-api-url/v1/chat/completions"
    export DEBUGBOT_API_KEY="your-api-key"
    export DEBUGBOT_MODEL="gpt-4o"
    python agent.py

    # 方式三：运行时交互输入
    python agent.py
"""

import os
import sys
import json
import subprocess
import re
import time
import ssl
import argparse

from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ============== 配置区 ==============
API_URL = os.environ.get('DEBUGBOT_API_URL', 'https://your-api-url/v1/chat/completions')
API_KEY = os.environ.get('DEBUGBOT_API_KEY', 'your-api-key')
MODEL = os.environ.get('DEBUGBOT_MODEL', 'gpt-4o')

# 允许执行的命令白名单（正则匹配）
ALLOWED_COMMANDS = [
    # ========== 文件操作 ==========
    r'^cat\s+',           # 读取文件
    r'^head\s+',          # 查看文件头部
    r'^tail\s+',          # 查看文件尾部
    r'^grep\s+',          # 搜索
    r'^awk\s+',           # 文本处理
    r'^sed\s+',           # 文本处理
    r'^sort\s+',          # 排序
    r'^uniq\s+',          # 去重
    r'^cut\s+',           # 列提取
    r'^wc\s+',            # 计数
    r'^diff\s+',          # 比较文件
    r'^ls\s*',            # 列出目录
    r'^pwd$',             # 当前目录
    r'^cd\s+',            # 切换目录
    r'^find\s+',          # 文件搜索
    r'^which\s+',         # 查找命令
    r'^whereis\s+',       # 查找命令位置
    r'^stat\s+',          # 文件状态
    r'^file\s+',          # 文件类型
    r'^md5sum\s+',        # MD5 校验
    r'^sha256sum\s+',     # SHA256 校验
    r'^sha1sum\s+',       # SHA1 校验
    r'^tar\s+',           # 解压归档
    r'^gzip\s+',          # gzip 压缩
    r'^gunzip\s+',        # gzip 解压
    r'^zip\s+',           # zip 压缩
    r'^unzip\s+',         # zip 解压
    r'^zcat\s+',          # 读取压缩文件
    r'^zgrep\s+',         # 搜索压缩文件
    r'^bzcat\s+',         # bz2 解压
    r'^xzcat\s+',         # xz 解压
    r'^less\s+',          # 分页查看
    r'^more\s+',          # 分页查看
    r'^touch\s+',         # 创建空文件

    # ========== 系统监控 ==========
    r'^ps\s+',            # 进程查看
    r'^top\s+',           # 系统监控
    r'^htop\s+',          # 系统监控
    r'^btop\s+',          # 系统监控
    r'^iotop\s+',         # IO 监控
    r'^iftop\s+',         # 网卡流量
    r'^vmstat\s+',        # 虚拟内存统计
    r'^mpstat\s+',        # CPU 统计
    r'^iostat\s+',        # IO 统计
    r'^sar\s+',           # 系统活动报告
    r'^uptime\s+',        # 运行时间
    r'^w\s+',             # 查看登录用户
    r'^who\s+',           # 查看登录用户
    r'^whoami\s+',        # 当前用户
    r'^id\s+',            # 用户信息
    r'^users\s+',         # 用户列表

    # ========== 资源使用 ==========
    r'^df\s+',            # 磁盘使用
    r'^du\s+',            # 目录大小
    r'^free\s+',          # 内存使用
    r'^cat\s+/proc/meminfo',  # 内存详情
    r'^cat\s+/proc/cpuinfo',  # CPU 详情
    r'^cat\s+/proc/loadavg',  # 负载情况
    r'^cat\s+/proc/diskstats', # 磁盘统计
    r'^cat\s+/proc/net/dev',  # 网卡统计
    r'^cat\s+/proc/stat',     # 系统统计

    # ========== 网络诊断 ==========
    r'^netstat\s+',       # 网络连接
    r'^ss\s+',            # 网络连接
    r'^ip\s+',            # IP 命令
    r'^ifconfig\s+',      # 网卡配置
    r'^route\s+',         # 路由表
    r'^arp\s+',           # ARP 表
    r'^ping\s+',          # 网络测试
    r'^traceroute\s+',    # 路由追踪
    r'^tracert\s+',       # 路由追踪 (Windows)
    r'^mtr\s+',           # 路由追踪
    r'^nslookup\s+',      # DNS 查询
    r'^dig\s+',           # DNS 查询
    r'^host\s+',          # DNS 查询
    r'^nmap\s+',          # 端口扫描
    r'^telnet\s+',        # 远程连接
    r'^nc\s+',            # 网络工具
    r'^curl\s+',          # HTTP 请求
    r'^wget\s+',          # 下载
    r'^httpie\s+',        # HTTP 客户端
    r'^tcpdump\s+',       # 网络抓包
    r'^ethool\s+',        # 网卡工具

    # ========== 服务管理 ==========
    r'^systemctl\s+',     # systemd 服务管理
    r'^service\s+',       # SysV 服务管理
    r'^journalctl\s+',    # 日志查看
    r'^chkconfig\s+',     # 服务开关
    r'^update-rc\.d\s+',  # 服务开关 (Debian)
    r'^supervisorctl\s+', # Supervisor 管理
    r'^pm2\s+',           # PM2 Node.js 管理

    # ========== Docker ==========
    r'^docker\s+ps\s+',    # 容器列表
    r'^docker\s+logs\s+',  # 容器日志
    r'^docker\s+exec\s+',  # 容器执行
    r'^docker\s+images\s+', # 镜像列表
    r'^docker\s+inspect\s+', # 容器信息
    r'^docker\s+stats\s+',  # 容器统计
    r'^docker\s+top\s+',    # 容器进程
    r'^docker\s+port\s+',   # 容器端口
    r'^docker\s+network\s+', # 网络管理
    r'^docker\s+volume\s+', # 卷管理
    r'^docker\s+info\s+',   # Docker 信息
    r'^docker\s+version\s+', # 版本信息
    r'^docker\s+container\s+ls\s+',  # 新语法
    r'^docker\s+image\s+ls\s+',      # 新语法

    # ========== Kubernetes ==========
    r'^kubectl\s+',       # K8s 命令
    r'^helm\s+',          # Helm 包管理
    r'^kubesec\s+',       # K8s 安全扫描
    r'^kustomize\s+',    # K8s 配置

    # ========== 数据库 ==========
    r'^mysql\s+',         # MySQL 客户端
    r'^mariadb\s+',       # MariaDB 客户端
    r'^psql\s+',          # PostgreSQL 客户端
    r'^redis-cli\s+',     # Redis 客户端
    r'^mongosh\s+',       # MongoDB Shell
    r'^mongo\s+',         # MongoDB (旧版)
    r'^sqlite3\s+',       # SQLite

    # ========== Web 服务器 ==========
    r'^nginx\s+',         # Nginx
    r'^apachectl\s+',     # Apache
    r'^httpd\s+',         # Apache
    r'^caddy\s+',         # Caddy

    # ========== 中间件 ==========
    r'^rabbitmqctl\s+',   # RabbitMQ
    r'^kafka-topics\s+',  # Kafka
    r'^kafka-console-consumer\s+',  # Kafka 消费者
    r'^zookeeper-cli\s+', # ZooKeeper
    r'^etcdctl\s+',       # etcd

    # ========== 编程语言 ==========
    r'^python[23]?\s+',   # Python
    r'^python[23]?\s+-m\s+',  # Python 模块
    r'^pip\s+',           # pip
    r'^pip3\s+',          # pip3
    r'^pip2\s+',         # pip2
    r'^node\s+',          # Node.js
    r'^npm\s+',           # NPM
    r'^npx\s+',           # NPX
    r'^yarn\s+',          # Yarn
    r'^pnpm\s+',          # pnpm
    r'^java\s+',          # Java
    r'^javac\s+',         # Java 编译
    r'^mvn\s+',           # Maven
    r'^gradle\s+',        # Gradle
    r'^go\s+',            # Go
    r'^cargo\s+',         # Rust
    r'^ruby\s+',          # Ruby
    r'^gem\s+',           # Ruby Gem
    r'^bundle\s+',        # Ruby Bundle
    r'^php\s+',           # PHP
    r'^composer\s+',      # PHP Composer

    # ========== CI/CD ==========
    r'^git\s+',           # Git
    r'^svn\s+',           # SVN
    r'^hg\s+',            # Mercurial
    r'^jenkins\s+',       # Jenkins
    r'^gitlab-runner\s+', # GitLab Runner
    r'^ansible\s+',       # Ansible
    r'^terraform\s+',     # Terraform
    r'^packer\s+',        # Packer
    r'^vault\s+',         # HashiCorp Vault
    r'^nomad\s+',         # Nomad
    r'^consul\s+',       # Consul

    # ========== 容器编排 ==========
    r'^docker-compose\s+',  # Docker Compose
    r'^docker stack\s+',    # Docker Stack
    r'^podman\s+',          # Podman
    r'^crictl\s+',          # CRI 工具
    r'^nerdctl\s+',         # containerd 工具

    # ========== 日志分析 ==========
    r'^logger\s+',         # 系统日志
    r'^dmesg\s+',          # 内核日志
    r'^last\s+',           # 登录记录
    r'^lastlog\s+',        # 最后登录
    r'^faillog\s+',        # 失败登录

    # ========== 系统信息 ==========
    r'^uname\s+',         # 系统信息
    r'^hostname\s+',      # 主机名
    r'^cat\s+/etc/os-release',  # OS 版本
    r'^lsb_release\s+',   # Linux 版本
    r'^arch\s+',          # 架构
    r'^lscpu\s+',         # CPU 信息
    r'^lsblk\s+',         # 块设备
    r'^lspci\s+',         # PCI 设备
    r'^lsusb\s+',         # USB 设备
    r'^dmidecode\s+',     # 硬件信息
    r'^cat\s+/proc/interrupts', # 中断信息
    r'^cat\s+/proc/uptime',     # 运行时间

    # ========== 进程与资源 ==========
    r'^lsof\s+',          # 查看打开的文件
    r'^strace\s+',        # 追踪系统调用
    r'^ltrace\s+',        # 追踪库调用
    r'^pstack\s+',        # 进程堆栈
    r'^pidof\s+',         # 查找进程 ID
    r'^pgrep\s+',         # 查找进程
    r'^pkill\s+',         # 杀死进程 (谨慎)
    r'^kill\s+',          # 杀死进程 (谨慎)
    r'^nice\s+',          # 调整进程优先级
    r'^renice\s+',        # 修改进程优先级
    r'^nohup\s+',         # 后台运行
    r'^screen\s+',        # 终端复用
    r'^tmux\s+',          # 终端复用

    # ========== 调试工具 ==========
    r'^gdb\s+',           # GDB 调试器
    r'^valgrind\s+',      # 内存检查
    r'^perf\s+',          # 性能分析
    r'^ebpf-tools\s+',    # eBPF
    r'^bpftrace\s+',      # BPF 追踪
    r'^flamegraph\s+',    # 火焰图
    r'^curl\s+-v\s+',     # 详细 HTTP
    r'^curl\s+-I\s+',     # HTTP 头
    r'^openssl\s+s_client\s+',  # SSL 测试
    r'^keytool\s+',       # Java 密钥工具

    # ========== 杂项 ==========
    r'^cron\s+',          # Cron
    r'^crontab\s+',       # Crontab
    r'^at\s+',            # 一次性任务
    r'^watch\s+',         # 监控命令
    r'^xargs\s+',         # 参数构建
    r'^date\s+',          # 日期时间
    r'^time\s+',          # 执行计时
    r'^sleep\s+',         # 延时
    r'^timeout\s+',       # 超时执行
    r'^bg\s+',            # 后台任务
    r'^fg\s+',            # 前台任务
    r'^jobs\s+',          # 任务列表
    r'^alias\s+',         # 命令别名
    r'^unalias\s+',       # 删除别名
    r'^history\s+',       # 命令历史
    r'^export\s+',        # 环境变量
    r'^type\s+',          # 命令类型
    r'^man\s+',           # 帮助手册
    r'^help\s+',          # 帮助
]

# 禁止的命令模式
FORBIDDEN_PATTERNS = [
    # ========== 危险文件操作 ==========
    r'rm\s+-rf\s+/',           # 删根目录
    r'rm\s+-rf\s+/\s',         # 删根目录变体
    r'rm\s+-rf\s+\*',          # 递归删除
    r'rm\s+-r\s+/',            # 递归删除根目录
    r'dd\s+.*of=/dev/',        # 直接写设备
    r'dd\s+.*of=/dev/sd',      # 直接写磁盘
    r'mkfs\s+',                # 格式化
    r'mkfs\.\w+\s+',           # 格式化
    r':\(\)\{',                # Bash 破壳
    r'>\s*/dev/sd',            # 写磁盘设备
    r'>\s*/dev/hd',            # 写磁盘设备
    r'>\s*/etc/passwd',        # 覆盖密码文件
    r'>\s*/etc/shadow',        # 覆盖影子文件
    r'>\s*/etc/group',         # 覆盖组文件
    r'mkdir\s+/proc',          # 创建 /proc
    r'unmount\s+-f\s+/',       # 强制卸载根
    r'umount\s+-f\s+/',        # 强制卸载根
    r'passwd\s+root',          # 修改 root 密码

    # ========== 系统控制 ==========
    r'shutdown',               # 关机
    r'poweroff',               # 关机
    r'reboot',                 # 重启
    r'halt',                   # 关机
    r'init\s+0',               # 关机
    r'init\s+6',               # 重启
    r'telinit\s+0',            # 关机
    r'telinit\s+6',            # 重启
    r'pkill\s+-9\s+kernel',    # 杀内核进程
    r'kill\s+-9\s+1',         # 杀 init 进程
    r'killall\s+-9',          # 杀死所有进程
    r'kill\s+-9\s+-1',        # 杀死所有进程

    # ========== 权限相关 ==========
    r'chmod\s+777\s+/',        # 开放根目录权限
    r'chmod\s+-R\s+777\s+/',   # 递归开放权限
    r'chmod\s+4755',          # 设置 SUID
    r'chown\s+-R\s+',         # 修改所有者
    r'chgrp\s+-R\s+',         # 修改组
    r'setfacl\s+',             # 修改 ACL
    r'getfacl\s+',             # 读取 ACL (这个可以放行)

    # ========== 网络安全 ==========
    r'iptables\s+-F',          # 清空防火墙
    r'iptables\s+-X',          # 删除防火墙规则
    r'iptables\s+-Z',          # 清零计数器
    r'ip\s+link\s+set\s+down', # 关闭网卡
    r'ifconfig\s+\w+\s+down',  # 关闭网卡
    r'service\s+iptables\s+stop', # 关闭防火墙
    r'ufw\s+disable',          # 关闭 UFW

    # ========== 危险命令 ==========
    r'mount\s+--bind\s+/',     # 绑定挂载
    r'mount\s+.*proc\s+/',     # 挂载 proc
    r'chroot\s+',             # 切换根目录
    r'eval\s+',               # 危险 eval
    r'exec\s+',               # 执行命令
    r'source\s+.*\|',         # 管道执行
]

# 文件访问限制（允许的目录或路径前缀）
ALLOWED_PATHS = [
    '/',
    '/home',
    '/opt',
    '/var/log',
    '/var/www',
    '/etc',
    '/tmp',
    '/root',
    '/app',
    '/usr/local',
    '/data',
    '/workspace',
    '/srv',
    '/www',
    '.',
    '..',
]

MAX_FILE_SIZE = 1024 * 1024  # 最大读取 1MB
MAX_OUTPUT_LINES = 500       # 最大输出行数
MAX_TOOL_CONTENT = 8000      # 工具结果最大字符数（送给 LLM 的）
MAX_DISPLAY_CHARS = 2000     # 终端显示截断字符数
COMMAND_TIMEOUT = 30         # 命令超时秒数
MAX_MESSAGES = 30            # 消息滑动窗口大小（超过后压缩）
COMPRESS_KEEP_RECENT = 10   # 压缩时保留最近 N 条消息，其余用 LLM 摘要替代

# ============== 工作区 ==============

def setup_workspace():
    """创建并返回工作区路径（debugbot-workspace/memories + scripts/）"""
    base = os.environ.get('DEBUGBOT_WORKSPACE', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debugbot-workspace'))
    for sub in ['memories', 'scripts']:
        path = os.path.join(base, sub)
        if not os.path.exists(path):
            os.makedirs(path)
    return base

WORKSPACE = setup_workspace()

# 全局任务列表（todo_write 工具维护）
TODO_LIST = []

# 本次会话 ID（用于 scripts/ 按时间戳隔离）
SESSION_ID = time.strftime('%Y%m%d_%H%M%S')

def _update_memory_index(filepath, content):
    """自动维护 MEMORY.md 索引：从 memory 文件的 frontmatter 提取 name/description"""
    import re as _re
    memory_index = os.path.join(WORKSPACE, 'memories', 'MEMORY.md')
    # 提取 frontmatter
    name = os.path.basename(filepath).rsplit('.', 1)[0]
    description = ""
    m = _re.search(r'description:\s*(.+)', content)
    if m:
        description = m.group(1).strip()
    entry = "- [{}]({}) — {}".format(name, os.path.basename(filepath), description or name)

    # 读取现有索引
    existing = []
    if os.path.exists(memory_index):
        with open(memory_index, 'r', encoding='utf-8', errors='ignore') as f:
            existing = [l.rstrip() for l in f.readlines() if l.strip()]

    # 更新或追加（按文件名去重）
    basename = os.path.basename(filepath)
    updated = False
    for i, line in enumerate(existing):
        if basename in line:
            existing[i] = entry
            updated = True
            break
    if not updated:
        existing.append(entry)

    with open(memory_index, 'w', encoding='utf-8') as f:
        f.write('\n'.join(existing) + '\n')

# ============== 工具函数 ==============

def truncate_output(text, max_chars=MAX_TOOL_CONTENT):
    """智能截断：保留首尾，中间用标记替代。避免丢失关键日志信息"""
    if len(text) <= max_chars:
        return text
    head_size = max_chars * 2 // 3   # 前 2/3
    tail_size = max_chars // 3       # 后 1/3
    return (text[:head_size]
            + "\n\n...[中间已截断，共 {} 字符，保留前 {} + 后 {} 字符]...\n\n".format(
                len(text), head_size, tail_size)
            + text[-tail_size:])

def strip_markdown(text):
    """洗掉 Markdown 语法，适合终端显示"""
    import re as _re
    # 去掉 **bold** 和 *italic*
    text = _re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = _re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', text)
    # 去掉 `code` 标记
    text = _re.sub(r'`([^`]+)`', r'\1', text)
    # 去掉 ## ### 标题标记
    text = _re.sub(r'^#{1,6}\s+', '', text, flags=_re.MULTILINE)
    # 去掉 Markdown 表格的 | 分隔线（保留内容）
    # 先处理表头分隔行 |---|---| 这种
    text = _re.sub(r'^\|[\s\-:|]+\|$', '', text, flags=_re.MULTILINE)
    # 去掉表格每行的首尾 |
    text = _re.sub(r'^\|(.+)\|$', r'  \1', text, flags=_re.MULTILINE)
    # 去掉水平线 --- *** ===
    text = _re.sub(r'^[\-*=_]{3,}\s*$', '', text, flags=_re.MULTILINE)
    # 去掉多余空行
    text = _re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def print_msg(msg, color=None):
    """带颜色的打印"""
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'end': '\033[0m',
    }
    if color and color in colors and sys.stdout.isatty():
        print(colors[color] + msg + colors['end'])
    else:
        print(msg)

def print_error(msg):
    print_msg("[ERROR] " + msg, 'red')

def print_warn(msg):
    print_msg("[WARN]  " + msg, 'yellow')

def print_info(msg):
    print_msg("[INFO]  " + msg, 'cyan')

def print_success(msg):
    print_msg("[OK]    " + msg, 'green')

def is_path_allowed(path):
    """检查路径是否在允许范围内"""
    if not path:
        return False

    # 处理相对路径
    if not path.startswith('/'):
        path = os.path.join(os.getcwd(), path)

    abs_path = os.path.abspath(path)

    for allowed in ALLOWED_PATHS:
        if abs_path == allowed or abs_path.startswith(allowed + '/'):
            return True
    return False

def is_command_allowed(cmd):
    """检查命令是否在白名单中"""
    if not cmd:
        return False, "空命令"

    cmd = cmd.strip()

    # 检查禁止模式 - 危险命令直接拒绝
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, cmd):
            return False, "禁止执行的危险命令: 匹配到 {}".format(pattern)

    # 检查白名单
    for pattern in ALLOWED_COMMANDS:
        if re.match(pattern, cmd):
            return True, "OK"

    # 不在白名单中但不是危险命令 - 需要用户确认
    return None, "命令不在白名单中，需要确认: {}".format(cmd[:50])

# 安全只读命令（不需要确认直接执行）
SAFE_READONLY_PATTERNS = [
    # 文件读取
    r'^cat\s+', r'^head\s+', r'^tail\s+', r'^grep\s+', r'^awk\s+',
    r'^sed\s+', r'^wc\s+', r'^sort\s+', r'^uniq\s+', r'^cut\s+',
    r'^less\s+', r'^more\s+', r'^zcat\s+', r'^zgrep\s+', r'^diff\s+',
    # 目录查看
    r'^ls\s*', r'^pwd$', r'^cd\s+', r'^find\s+', r'^which\s+',
    r'^whereis\s+', r'^locate\s+', r'^stat\s+', r'^file\s+',
    # 进程查看
    r'^ps\s+', r'^top\s+', r'^htop\s+', r'^btop\s+', r'^pgrep\s+',
    r'^pidof\s+', r'^pstree\s+', r'^watch\s+',
    # 网络诊断
    r'^curl\s+', r'^wget\s+', r'^ping\s+', r'^netstat\s+', r'^ss\s+',
    r'^nslookup\s+', r'^dig\s+', r'^host\s+', r'^traceroute\s+',
    r'^mtr\s+', r'^tcpdump\s+', r'^nmap\s+', r'^telnet\s+', r'^nc\s+',
    r'^ip\s+', r'^ifconfig\s+', r'^route\s+', r'^arp\s+',
    # 系统信息
    r'^df\s+', r'^du\s+', r'^free\s+', r'^uptime\s+', r'^w\s+',
    r'^who\s+', r'^whoami\s+', r'^id\s+', r'^users\s+',
    r'^uname\s+', r'^hostname\s+', r'^arch\s+',
    r'^lscpu\s+', r'^lsblk\s+', r'^lspci\s+', r'^lsusb\s+',
    r'^lsof\s+', r'^dmesg\s+',
    # 性能监控
    r'^vmstat\s+', r'^iostat\s+', r'^mpstat\s+', r'^sar\s+',
    r'^iotop\s+', r'^iftop\s+',
    # 日志查看
    r'^journalctl\s+', r'^last\s+', r'^lastlog\s+', r'^faillog\s+',
    # Docker 只读
    r'^docker\s+ps\s+', r'^docker\s+logs\s+', r'^docker\s+images\s+',
    r'^docker\s+inspect\s+', r'^docker\s+stats\s+', r'^docker\s+top\s+',
    r'^docker\s+port\s+', r'^docker\s+info\s+', r'^docker\s+version\s+',
    r'^docker\s+network\s+ls\s+', r'^docker\s+volume\s+ls\s+',
    r'^docker\s+container\s+ls\s+', r'^docker\s+image\s+ls\s+',
    # K8s 只读
    r'^kubectl\s+get\s+', r'^kubectl\s+describe\s+', r'^kubectl\s+logs\s+',
    r'^kubectl\s+top\s+', r'^kubectl\s+events\s+', r'^kubectl\s+cluster-info\s+',
    r'^kubectl\s+api-resources\s+', r'^kubectl\s+api-versions\s+',
    r'^kubectl\s+config\s+view\s+',
    # Git 只读
    r'^git\s+log\s+', r'^git\s+status\s+', r'^git\s+diff\s+',
    r'^git\s+show\s+', r'^git\s+branch\s+', r'^git\s+tag\s+',
    r'^git\s+remote\s+-v\s+', r'^git\s+stash\s+list\s+',
    # 数据库只读
    r'^mysql\s+.*-e\s+["\']\s*SELECT', r'^mysql\s+.*--execute\s+["\']\s*SELECT',
    r'^psql\s+.*-c\s+["\']\s*SELECT', r'^redis-cli\s+GET\s+',
    r'^redis-cli\s+SCAN\s+', r'^redis-cli\s+INFO\s+', r'^redis-cli\s+TYPE\s+',
    r'^redis-cli\s+KEYS\s+', r'^redis-cli\s+TTL\s+',
    # 其他只读
    r'^env\s+', r'^printenv\s+', r'^type\s+', r'^alias\s+', r'^history\s+',
    r'^cat\s+/proc/', r'^md5sum\s+', r'^sha256sum\s+',
]

def is_safe_readonly_command(cmd):
    """检查是否是安全的只读命令（不需要确认）"""
    if not cmd:
        return False
    cmd = cmd.strip()
    for pattern in SAFE_READONLY_PATTERNS:
        if re.match(pattern, cmd):
            return True
    return False

def safe_read_file(filepath):
    """安全读取文件"""
    if not filepath:
        return None, "文件路径为空"

    if not is_path_allowed(filepath):
        return None, "路径不在允许范围内: {}".format(filepath)

    if not os.path.exists(filepath):
        return None, "文件不存在: {}".format(filepath)

    if not os.path.isfile(filepath):
        return None, "不是文件: {}".format(filepath)

    try:
        # 检查文件大小
        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE:
            return None, "文件超过 {} 字节限制".format(MAX_FILE_SIZE)

        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

        # 限制行数（保留首尾）
        lines = content.split('\n')
        if len(lines) > MAX_OUTPUT_LINES:
            head_lines = int(MAX_OUTPUT_LINES * 2 / 3)
            tail_lines = MAX_OUTPUT_LINES - head_lines
            content = '\n'.join(lines[:head_lines])
            content += "\n\n...[文件过长，共 {} 行，保留前 {} + 后 {} 行]...\n\n".format(
                len(lines), head_lines, tail_lines)
            content += '\n'.join(lines[-tail_lines:])

        return content, None
    except Exception as e:
        return None, str(e)

def execute_command(cmd, timeout=COMMAND_TIMEOUT):
    """安全执行命令"""
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            cwd=os.getcwd()
        )
        stdout, stderr = process.communicate(timeout=timeout)

        output = stdout.decode('utf-8', errors='ignore')
        err = stderr.decode('utf-8', errors='ignore')

        if err:
            output += "\n[STDERR]\n" + err

        # 限制输出行数（保留首尾）
        lines = output.split('\n')
        if len(lines) > MAX_OUTPUT_LINES:
            head_lines = int(MAX_OUTPUT_LINES * 2 / 3)
            tail_lines = MAX_OUTPUT_LINES - head_lines
            output = '\n'.join(lines[:head_lines])
            output += "\n\n...[输出过长，共 {} 行，保留前 {} + 后 {} 行]...\n\n".format(
                len(lines), head_lines, tail_lines)
            output += '\n'.join(lines[-tail_lines:])

        return output if output else "[命令无输出]", None
    except subprocess.TimeoutExpired:
        process.kill()
        return None, "命令执行超时 ({}秒)".format(timeout)
    except Exception as e:
        return None, str(e)

def request_confirmation(cmd, tool_name):
    """请求用户确认"""
    print()
    print_msg("  +" + "-" * 56 + "+", 'yellow')
    print_msg("  | {} — 需要确认:".format(tool_name), 'yellow')
    print_msg("  | " + cmd, 'white')
    print_msg("  +" + "-" * 56 + "+", 'yellow')
    print()

    while True:
        try:
            response = input("确认执行? (y/n/q): ").strip().lower()
            if response == 'y':
                return True
            elif response == 'n':
                return False
            elif response == 'q':
                print_info("操作已取消")
                return False
            else:
                print_warn("请输入 y (是) / n (否) / q (退出)")
        except (KeyboardInterrupt, EOFError):
            print_info("\n操作已取消")
            return False

# ============== LLM API 调用 ==============

def call_llm(messages, tools=None, temperature=0.7, max_tokens=None, stream=False):
    """调用 LLM API（支持 streaming 实时输出）"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + API_KEY
    }

    payload = {
        'model': MODEL,
        'messages': messages,
        'temperature': temperature,
    }

    if max_tokens:
        payload['max_tokens'] = max_tokens

    # DeepSeek 特殊参数：禁用思考模式
    if 'deepseek' in API_URL.lower():
        payload['thinking'] = {"type": "disabled"}

    # 调试模式：打印发送的消息
    if ARGS.debug:
        print_msg("\n[DEBUG] 发送的消息:", 'magenta')
        for i, msg in enumerate(messages):
            role = msg.get('role')
            tc = msg.get('tool_calls')
            print_msg("  [{}] role={}, has_tool_calls={}".format(i, role, bool(tc)), 'white')
            if tc:
                for t in tc:
                    print_msg("      -> id={}, func={}".format(t.get('id'), t['function']['name']), 'white')
            if role == 'tool':
                print_msg("      -> tool_call_id={}, content_len={}".format(msg.get('tool_call_id'), len(msg.get('content',''))), 'white')

    if tools:
        payload['tools'] = tools

    if stream:
        payload['stream'] = True
        return _call_llm_stream(headers, payload)

    data = json.dumps(payload).encode('utf-8')

    # 重试机制
    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = Request(API_URL, data=data, headers=headers)

            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            response = urlopen(req, timeout=120, context=ssl_context)

            result = response.read().decode('utf-8')

            return json.loads(result), None

        except HTTPError as e:
            error_body = e.read().decode('utf-8') if hasattr(e, 'read') else ''
            return None, "HTTP Error {}: {}".format(e.code, error_body)
        except URLError as e:
            if attempt < max_retries - 1:
                print_warn("连接失败，{} 秒后重试... ({}/{})".format(2 ** attempt, attempt + 1, max_retries))
                time.sleep(2 ** attempt)
                continue
            return None, "URL Error: " + str(e.reason)
        except Exception as e:
            if attempt < max_retries - 1:
                print_warn("请求失败，重试中... ({}/{})".format(attempt + 1, max_retries))
                time.sleep(2 ** attempt)
                continue
            return None, "Error: " + str(e)


def _call_llm_stream(headers, payload):
    """SSE streaming 调用：实时打印内容，返回累积的完整结果"""
    data = json.dumps(payload).encode('utf-8')

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    try:
        req = Request(API_URL, data=data, headers=headers)
        response = urlopen(req, timeout=120, context=ssl_context)

        accumulated_content = ""
        accumulated_tool_calls = {}  # index -> {id, function: {name, arguments}}
        finish_reason = None
        first_content = True

        for line in response:
            line = line.decode('utf-8').strip()
            if not line:
                continue
            if line.startswith('data: '):
                data_str = line[6:]
                if data_str == '[DONE]':
                    break
                try:
                    chunk = json.loads(data_str)
                    choices = chunk.get('choices', [])
                    if not choices:
                        continue
                    delta = choices[0].get('delta', {})

                    # 内容增量 — 实时打印
                    if 'content' in delta and delta['content']:
                        content_piece = delta['content']
                        if first_content:
                            print()  # 在首个内容块前换行
                            first_content = False
                        sys.stdout.write(strip_markdown(content_piece))
                        sys.stdout.flush()
                        accumulated_content += content_piece

                    # 工具调用增量 — 跨 chunk 累积
                    if 'tool_calls' in delta:
                        for tc in delta['tool_calls']:
                            idx = tc.get('index', 0)
                            if idx not in accumulated_tool_calls:
                                accumulated_tool_calls[idx] = {
                                    'id': '',
                                    'function': {'name': '', 'arguments': ''}
                                }
                            tc_acc = accumulated_tool_calls[idx]
                            if 'id' in tc and tc['id']:
                                tc_acc['id'] = tc['id']
                            if 'function' in tc:
                                if 'name' in tc['function'] and tc['function']['name']:
                                    tc_acc['function']['name'] = tc['function']['name']
                                if 'arguments' in tc['function']:
                                    tc_acc['function']['arguments'] += tc['function']['arguments']

                    if choices[0].get('finish_reason'):
                        finish_reason = choices[0]['finish_reason']

                except json.JSONDecodeError:
                    continue

        # 构造与非 streaming 一致的返回格式
        message = {"role": "assistant", "content": accumulated_content}
        if accumulated_tool_calls:
            tool_calls_list = []
            for idx in sorted(accumulated_tool_calls.keys()):
                tc = accumulated_tool_calls[idx]
                tool_calls_list.append({
                    'id': tc['id'],
                    'type': 'function',
                    'function': tc['function']
                })
            message['tool_calls'] = tool_calls_list

        result = {
            'choices': [{
                'message': message,
                'finish_reason': finish_reason or 'stop'
            }]
        }
        return result, None

    except HTTPError as e:
        error_body = e.read().decode('utf-8') if hasattr(e, 'read') else ''
        return None, "HTTP Error {}: {}".format(e.code, error_body)
    except Exception as e:
        return None, "Stream Error: " + str(e)

# ============== 上下文压缩 ==============

def compress_history(old_messages):
    """用 LLM 将历史消息压缩为摘要，保留关键排查信息"""
    compress_prompt = """你是一个运维排查助手，请将以下对话历史压缩为一段简洁的摘要。

要求：
1. 保留用户最初的问题是什么
2. 保留已经执行了哪些关键命令及其重要发现
3. 保留已经得出的结论和排查方向
4. 保留当前待解决的问题
5. 忽略冗余的对话细节和无关内容
6. 用中文输出，控制在 500 字以内

对话历史：
---
"""
    for msg in old_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if role == "tool":
            content = content[:500] + ("..." if len(content) > 500 else "")
        compress_prompt += "\n[{}]: {}".format(role, content)

    compress_prompt += "\n---\n请输出摘要："

    try:
        result, error = call_llm(
            [{"role": "user", "content": compress_prompt}],
            tools=None,
            temperature=0.3,
            max_tokens=600,
        )
        if error:
            print_warn("历史压缩失败: {}".format(error))
            return None
        summary = result["choices"][0]["message"]["content"]
        return summary.strip()
    except Exception as e:
        print_warn("历史压缩失败: {}".format(e))
        return None

# ============== 工具定义 ==============

def get_tools():
    """获取可用的工具定义"""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "读取文件内容。用于查看日志、配置、代码等。谨慎使用，只读取必要的文件。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "要读取的文件路径"
                        }
                    },
                    "required": ["filepath"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "执行 Linux 命令。用于查看进程、日志、调试网络等。只使用只读命令，不要执行修改操作。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的命令"
                        }
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "列出目录内容。用于查看文件夹结构。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "目录路径，默认为当前目录"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "env_snapshot",
                "description": "一键收集当前环境快照信息（主机名、IP、内存、磁盘、进程、环境变量、网络端口等）。适合排查开始时快速了解环境状态。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_processes": {
                            "type": "boolean",
                            "description": "是否包含进程列表，默认 true"
                        },
                        "include_network": {
                            "type": "boolean",
                            "description": "是否包含网络连接信息，默认 true"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "在工作区内写入文件（记忆、临时脚本等）。文件只能写入 debugbot-workspace 目录内，禁止写入外部路径。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filepath": {
                            "type": "string",
                            "description": "文件路径（相对于工作区或绝对路径，自动限制在工作区内）"
                        },
                        "content": {
                            "type": "string",
                            "description": "要写入的文件内容"
                        }
                    },
                    "required": ["filepath", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "todo_write",
                "description": "创建和管理任务列表，用于跟踪多步排查进度。任务以 JSON 格式在内部维护，支持创建、标记完成、查看。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["add", "complete", "list"],
                            "description": "操作: add(添加任务), complete(标记完成), list(查看所有)"
                        },
                        "task": {
                            "type": "string",
                            "description": "任务描述 (add 时必填)"
                        },
                        "task_id": {
                            "type": "integer",
                            "description": "任务编号 (complete 时必填)"
                        }
                    },
                    "required": ["action"]
                }
            }
        }
    ]

def execute_tool(tool_name, tool_input):
    """执行工具"""
    if tool_name == "read_file":
        filepath = tool_input.get("filepath", "")

        content, error = safe_read_file(filepath)
        if error:
            return "读取文件失败: " + error
        return content if content else "[空文件]"

    elif tool_name == "run_command":
        command = tool_input.get("command", "")

        # 检查命令是否在白名单中
        allowed, reason = is_command_allowed(command)

        if allowed == False:
            # 危险命令，直接拒绝
            return "命令不允许: " + reason

        # 安全只读命令直接执行
        if is_safe_readonly_command(command):
            output, error = execute_command(command)
            if error:
                return "命令执行失败: " + error
            return output if output else "[命令无输出]"

        # 不在白名单或非只读命令 → 让用户确认
        if request_confirmation(command, "Bash"):
            output, error = execute_command(command)
            if error:
                return "命令执行失败: " + error
            return output if output else "[命令无输出]"
        else:
            return "[已取消] 用户拒绝执行该命令"

    elif tool_name == "list_directory":
        path = tool_input.get("path", ".")

        if not is_path_allowed(path):
            return "路径不在允许范围内"

        try:
            items = os.listdir(path)

            items.sort()
            result = []
            for item in items:
                full_path = os.path.join(path, item)
                try:
                    if os.path.isdir(full_path):
                        result.append(item + "/")
                    else:
                        size = os.path.getsize(full_path)
                        result.append(item + " ({})".format(format_size(size)))
                except:
                    result.append(item)

            return '\n'.join(result) if result else "[空目录]"
        except Exception as e:
            return "列出目录失败: " + str(e)

    elif tool_name == "env_snapshot":
        include_proc = tool_input.get("include_processes", True)
        include_net = tool_input.get("include_network", True)
        return run_env_snapshot(include_proc, include_net)

    elif tool_name == "write_file":
        filepath = tool_input.get("filepath", "")
        content = tool_input.get("content", "")

        if not filepath:
            return "文件路径为空"

        # 如果传的是相对路径，拼到工作区下
        if not filepath.startswith('/'):
            # scripts/ 下的文件自动路由到本次会话子目录
            if filepath.startswith('scripts/') or filepath.startswith('scripts\\'):
                rel = filepath[len('scripts/'):] if filepath.startswith('scripts/') else filepath[len('scripts\\'):]
                filepath = os.path.join(WORKSPACE, 'scripts', SESSION_ID, rel)
            else:
                filepath = os.path.join(WORKSPACE, filepath)
        else:
            # 绝对路径：校验是否在工作区内，不在则拒接（防 ../ 逃逸）
            abs_path = os.path.abspath(filepath)
            ws_abs = os.path.abspath(WORKSPACE)
            if not abs_path.startswith(ws_abs + os.sep) and abs_path != ws_abs:
                return "文件路径不在工作区内: {}（仅允许写入 {}/）".format(filepath, WORKSPACE)

        try:
            # 确保父目录存在
            parent = os.path.dirname(os.path.abspath(filepath))
            if not os.path.exists(parent):
                os.makedirs(parent)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            # 自动维护 MEMORY.md 索引：写入 memories/ 目录时更新索引
            abs_path = os.path.abspath(filepath)
            memories_dir = os.path.join(WORKSPACE, 'memories')
            if abs_path.startswith(memories_dir + os.sep) and os.path.basename(filepath) != 'MEMORY.md':
                _update_memory_index(filepath, content)
            return "文件已写入: {}".format(filepath)
        except Exception as e:
            return "写入文件失败: {}".format(str(e))

    elif tool_name == "todo_write":
        action = tool_input.get("action", "list")
        if action == "add":
            task = tool_input.get("task", "")
            if not task:
                return "任务描述不能为空"
            tid = len(TODO_LIST) + 1
            TODO_LIST.append({"id": tid, "task": task, "status": "pending"})
            return "已添加任务 #{}: {}".format(tid, task)
        elif action == "complete":
            tid = tool_input.get("task_id", 0)
            for t in TODO_LIST:
                if t["id"] == tid:
                    t["status"] = "completed"
                    return "任务 #{} 已完成: {}".format(tid, t["task"])
            return "未找到任务 #{}".format(tid)
        elif action == "list":
            if not TODO_LIST:
                return "任务列表为空"
            lines = []
            for t in TODO_LIST:
                mark = "x" if t["status"] == "completed" else " "
                lines.append("  [{}] #{} {}".format(mark, t["id"], t["task"]))
            return "\n".join(lines)
        return "未知操作: {}".format(action)

    return "[未知工具: {}]".format(tool_name)

def run_env_snapshot(include_processes=True, include_network=True):
    """执行环境快照，一键收集关键信息"""
    sections = []

    # 基础信息
    commands_basic = [
        ("== 主机名 ==", "hostname"),
        ("== IP 地址 ==", "hostname -I 2>/dev/null || ifconfig 2>/dev/null | grep 'inet '"),
        ("== 操作系统 ==", "cat /etc/os-release 2>/dev/null | head -5"),
        ("== 内核版本 ==", "uname -a"),
        ("== 运行时间 ==", "uptime"),
        ("== 当前用户 ==", "whoami"),
        ("== 工作目录 ==", "pwd"),
        ("== 内存使用 ==", "free -h 2>/dev/null || cat /proc/meminfo | head -5"),
        ("== 磁盘使用 ==", "df -h 2>/dev/null | head -20"),
        ("== CPU 信息 ==", "nproc && cat /proc/loadavg"),
        ("== 环境变量 ==", "env | sort"),
    ]

    commands_process = [
        ("== 进程列表（按内存排序 Top 20）==", "ps aux --sort=-%mem 2>/dev/null | head -21 || ps aux | head -21"),
    ]

    commands_network = [
        ("== 监听端口 ==", "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null"),
        ("== 活跃连接数 ==", "ss -s 2>/dev/null || netstat -s 2>/dev/null | head -10"),
    ]

    all_commands = list(commands_basic)
    if include_processes:
        all_commands.extend(commands_process)
    if include_network:
        all_commands.extend(commands_network)

    for title, cmd in all_commands:
        output, error = execute_command(cmd, timeout=10)
        if error:
            sections.append("{}\n[获取失败: {}]".format(title, error))
        else:
            sections.append("{}\n{}".format(title, output))

    return "\n".join(sections)

def format_size(size):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return "{}{}".format(int(size), unit)
        size /= 1024.0
    return "{}{}".format(int(size), 'TB')

# ============== 主循环 ==============

def setup_config():
    """运行时配置"""
    global API_URL, API_KEY, MODEL, ARGS

    parser = argparse.ArgumentParser(description="Poor Man's DevOps Agent")
    parser.add_argument('-u', '--api-url', default=None, help='API endpoint')
    parser.add_argument('-k', '--api-key', default=None, help='API key')
    parser.add_argument('-m', '--model', default=None, help='Model name')
    parser.add_argument('-n', '--non-interactive', action='store_true', help='Non-interactive mode, exit on missing config')
    parser.add_argument('--no-stream', action='store_true', help='Disable streaming output')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    ARGS = parser.parse_args()

    print_msg("""
    ╔══════════════════════════════════════════════════════════════╗
    ║        Poor Man's DevOps Agent  —  乞丐版运维助手             ║
    ║        AI-Powered | Command Whitelist | Human-in-the-Loop   ║
    ╚══════════════════════════════════════════════════════════════╝
    """, 'cyan')

    print_msg("  Supported Tools", 'green')
    print_msg("  ┌──────────────┬───────────────────────────────────────────┐", 'white')
    print_msg("  │ System       │ ps, top, free, df, du, uptime, env       │", 'white')
    print_msg("  │ Network      │ curl, ping, netstat, ss, dig, nslookup   │", 'white')
    print_msg("  │ Docker / K8s │ ps, logs, inspect, stats, get, describe  │", 'white')
    print_msg("  │ Database     │ MySQL, PostgreSQL, Redis (read-only)     │", 'white')
    print_msg("  │ Snapshot     │ env_snapshot — 一键收集环境快照           │", 'white')
    print_msg("  └──────────────┴───────────────────────────────────────────┘", 'white')
    print()

    # 优先级: CLI args > env vars > 交互输入
    cli_url = ARGS.api_url
    cli_key = ARGS.api_key
    cli_model = ARGS.model
    env_url = os.environ.get('DEBUGBOT_API_URL', '')
    env_key = os.environ.get('DEBUGBOT_API_KEY', '')
    env_model = os.environ.get('DEBUGBOT_MODEL', '')

    API_URL = cli_url or env_url
    API_KEY = cli_key or env_key
    MODEL = cli_model or env_model or 'gpt-4o'

    # 都没提供才走交互输入，非交互模式直接报错退出
    if not API_URL or not API_KEY:
        if ARGS.non_interactive:
            print_error("API URL 和 API Key 不能为空! (非交互模式)")
            sys.exit(1)
        print_info("请输入 API 配置（或设置环境变量 DEBUGBOT_API_URL / DEBUGBOT_API_KEY）")
        print()
        print_msg("  API Endpoint: ", 'white')
        API_URL = input("  > ").strip()
        print_msg("  API Key:      ", 'white')
        API_KEY = input("  > ").strip()
        print_msg("  Model:        ", 'white')
        MODEL = input("  > ").strip() or 'gpt-4o'

    if not API_URL or not API_KEY:
        print_error("API URL 和 API Key 不能为空!")
        sys.exit(1)

    print()
    print_msg("  ┌────────────┬──────────────────────────────────────────────┐", 'white')
    print_msg("  │ Endpoint   │ {}".format(API_URL), 'white')
    print_msg("  │ Model      │ {}".format(MODEL), 'white')
    print_msg("  │ Safe Mode  │ ENABLED — whitelist + human approval", 'yellow')
    print_msg("  │ Stream     │ {}".format('ON (SSE)' if not ARGS.no_stream and os.environ.get('DEBUGBOT_STREAM', '1') != '0' else 'OFF'), 'white')
    print_msg("  │ Allowed    │ /home, /var/log, /etc, /tmp, /app, ...", 'white')
    print_msg("  │ Workspace   │ {}".format(WORKSPACE), 'white')
    print_msg("  └────────────┴──────────────────────────────────────────────┘", 'white')
    print()
    print_msg("  Type 'quit' to exit | 'help' or /help for usage | / 开头为斜杠命令", 'cyan')
    print()

def main():
    # 运行时配置
    setup_config()

    # 系统提示 - 兼容模式（不强制使用工具）
    system_prompt = """你是一个 Poor Man's DevOps Agent (乞丐版运维助手)，帮助用户排查生产环境问题。

你是专业的运维工程师，熟悉 Linux 系统、Docker、Kubernetes、各种中间件和数据库。

工作方式：
1. 如果用户需要你执行命令分析问题，先给出建议的命令
2. 如果用户说"执行"或"帮我运行"，你可以执行以下命令
3. 优先使用只读命令（cat, grep, tail, ps, docker logs 等）
4. 不要执行任何修改数据的命令
5. 排查开始时，建议先用 env_snapshot 工具一键收集环境信息

可用工具：
- read_file: 读取文件内容
- run_command: 执行 Linux 命令
- write_file: 写入工作区文件（记忆、探针脚本等），文件仅限写入工作区 ({})
- list_directory: 列出目录
- env_snapshot: 一键收集环境快照（主机名、IP、内存、磁盘、进程、端口等）
- todo_write: 管理排查任务列表（add/complete/list），跟踪多步排查进度

可用命令参考：
- 查看日志: cat, tail, grep, journalctl, docker logs
- 查看进程: ps, top, htop
- 查看网络: netstat, ss, curl, ping, dig
- 查看文件: ls, find, cat, head, tail
- Docker: docker ps, docker logs, docker exec
- K8s: kubectl get pods, kubectl logs

安全规则：
1. 只使用只读命令，不要执行修改操作
2. 不要执行 rm, chmod, chown 等危险命令
3. 发现问题后给出分析和解决建议

输出格式要求（终端显示，禁止 Markdown 语法）：
- 禁止使用 Markdown 表格（| --- | 这种），用等宽空格对齐代替
- 禁止使用 ** 加粗、## 标题、` 代码块等 Markdown 标记
- 禁止使用 --- 分隔线（会被终端误解析）
- 用 ASCII 分隔符（如 +---+---+ 或 =====）代替
- 用缩进（两个空格）表示层级
- 列表用 - 或数字
- 中文输出，简洁直接

当前工作目录: {}

当前用户: {}

Python 版本: {}""".format(WORKSPACE, os.getcwd(), os.environ.get('USER', 'unknown'), sys.version.split()[0])

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    tools = get_tools()

    while True:
        try:
            # 获取用户输入
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print_info("\n再见!")
            break

        if not user_input:
            continue

        # 多行输入：以 """ 或 ''' 开头进入多行模式，单独一行同样的引号结束
        if user_input in ('"""', "'''"):
            quote = user_input
            lines = []
            print_msg("  (多行输入模式，输入 {} 结束)".format(quote), 'cyan')
            while True:
                try:
                    line = input()
                    if line.strip() == quote:
                        break
                    lines.append(line)
                except (KeyboardInterrupt, EOFError):
                    print_info("\n已取消多行输入")
                    lines = []
                    break
            if lines:
                user_input = "\n".join(lines)
            else:
                continue

        if not user_input:
            continue

        # 斜杠命令
        if user_input.startswith('/'):
            cmd = user_input[1:].strip().lower()
            if cmd in ['quit', 'exit', 'q']:
                print_info("再见!")
                break
            elif cmd == 'help':
                # 复用 help 显示
                user_input = 'help'
                # 继续走正常流程，但 help 不发给 LLM
            elif cmd == 'clear':
                messages.clear()
                messages.append({"role": "system", "content": system_prompt})
                print_success("对话历史已清空")
                continue
            elif cmd == 'compact':
                # 手动触发压缩
                if len(messages) > 3:
                    system_msg = messages[0]
                    old_msgs = messages[1:]
                    print_msg("\n  --- 手动压缩中 ---", 'yellow')
                    summary = compress_history(old_msgs)
                    messages.clear()
                    messages.append(system_msg)
                    if summary:
                        messages.append({"role": "user", "content": "[历史摘要]\n\n" + summary})
                        print_success("压缩完成，摘要 {} 字".format(len(summary)))
                    else:
                        print_warn("压缩失败")
                else:
                    print_info("消息太少，无需压缩")
                continue
            elif cmd == 'snapshot':
                print_msg("\n" + run_env_snapshot(), 'white')
                continue
            elif cmd == 'tools':
                print_msg("""
  Available Tools
    read_file     — 读取文件内容
    run_command   — 执行 Linux 命令
    write_file     — 写入工作区文件
    list_directory — 列出目录结构
    env_snapshot  — 一键环境快照
""", 'cyan')
                continue
            elif cmd == 'todo':
                if not TODO_LIST:
                    print_info("任务列表为空")
                else:
                    for t in TODO_LIST:
                        mark = "[x]" if t["status"] == "completed" else "[ ]"
                        color = 'green' if t["status"] == "completed" else 'white'
                        print_msg("  {} #{} {}".format(mark, t["id"], t["task"]), color)
                continue
            elif cmd == 'workspace':
                print_msg("""
  Workspace: {}
  ├─ memories/  ({} 条记忆)
  └─ scripts/   ({} 个脚本)
""".format(WORKSPACE,
           len(os.listdir(os.path.join(WORKSPACE, 'memories'))) if os.path.exists(os.path.join(WORKSPACE, 'memories')) else 0,
           len(os.listdir(os.path.join(WORKSPACE, 'scripts'))) if os.path.exists(os.path.join(WORKSPACE, 'scripts')) else 0), 'cyan')
                continue
            else:
                print_warn("未知命令: /{}，输入 /help 查看可用命令".format(cmd))
                continue

        if user_input.lower() in ['quit', 'exit', 'q']:
            print_info("再见!")
            print_msg("  Tip: 排查结束后建议删除 agent.py 避免 API Key 泄露", 'yellow')
            break

        if user_input.lower() == 'help':
            print_msg("""
  ┌─ Usage ──────────────────────────────────────────────────────┐
  │  直接输入问题，Agent 会分析并给出排查建议                       │
  │  输入 '执行' 或 '帮我运行' 让 Agent 执行命令                    │
  │  多行输入: 首行输入 \"\"\" 或 '''，以同样的引号行结束             │
  │                                                              │
  │  Tools                                                       │
  │    read_file     — 读取文件内容（日志、配置、代码）             │
  │    run_command   — 执行 Linux 命令（白名单 + 人工确认）         │
  │    write_file    — 写入工作区文件（记忆、脚本）                 │
  │    todo_write    — 任务列表（多步排查进度跟踪）                 │
  │    list_directory — 列出目录结构                              │
  │    env_snapshot  — 一键收集环境快照（主机名/IP/内存/磁盘/进程）  │
  │                                                              │
  │  Slash Commands                                              │
  │    /help       — 显示帮助                                    │
  │    /quit       — 退出                                       │
  │    /clear      — 清空对话历史                                │
  │    /compact    — 手动压缩上下文                               │
  │    /snapshot   — 一键环境快照                                 │
  │    /todo       — 查看任务列表                                 │
  │    /tools      — 列出可用工具                                 │
  │    /workspace  — 查看工作区状态                               │
  │                                                              │
  │  Workspace: {}         │
  └──────────────────────────────────────────────────────────────┘
""".format(WORKSPACE), 'cyan')
            continue

        try:
            # 添加用户消息
            messages.append({"role": "user", "content": user_input})
            print_msg("  " + "\u2500" * 60, 'white')  # 每轮开始的分隔线

            # 主循环：处理可能的多次 tool_calls
            max_tool_rounds = 10  # 防止无限循环
            for round_num in range(max_tool_rounds):
                # 上下文压缩：超过 MAX_MESSAGES 时，用 LLM 摘要替代旧消息
                if len(messages) > MAX_MESSAGES:
                    system_msg = messages[0]  # 保留 system prompt
                    # 保留最近 COMPRESS_KEEP_RECENT 条，其余压缩
                    split_point = max(1, len(messages) - COMPRESS_KEEP_RECENT)
                    old_msgs = messages[1:split_point]  # 排除 system prompt
                    recent = messages[split_point:]

                    print_msg("\n  --- 上下文压缩中 ({} 条消息 → 保留最近 {} 条 + LLM 摘要) ---".format(
                        len(messages), len(recent)), 'yellow')

                    summary = compress_history(old_msgs)

                    messages.clear()
                    messages.append(system_msg)
                    if summary:
                        messages.append({
                            "role": "user",
                            "content": "[历史摘要] 以下是之前排查过程的摘要，请基于这些信息继续：\n\n" + summary
                        })
                        print_success("上下文压缩完成，摘要 {} 字".format(len(summary)))
                    else:
                        # 压缩失败，降级为简单提示
                        messages.append({
                            "role": "user",
                            "content": "[系统提示: 之前的对话轮次过多，已自动压缩。请基于当前上下文继续排查]"
                        })
                        print_warn("压缩失败，已降级为简单截断")
                    messages.extend(recent)

                # 调用 LLM（默认 streaming，除非 --no-stream 或 DEBUGBOT_STREAM=0）
                use_stream = not ARGS.no_stream and os.environ.get('DEBUGBOT_STREAM', '1') != '0'

                if not use_stream:
                    print_msg("\n  \u00b7\u00b7\u00b7 thinking \u00b7\u00b7\u00b7", 'magenta')

                result, error = call_llm(messages, tools, stream=use_stream)

                if error:
                    print_error("API 调用失败: " + error)
                    if round_num == 0:
                        messages.pop()  # 第一轮失败，移除用户消息
                    break

                # 处理响应
                if 'choices' not in result or not result['choices']:
                    print_error("无效的 API 响应")
                    if round_num == 0:
                        messages.pop()
                    break

                choice = result['choices'][0]
                message = choice.get('message', {})

                # 处理 tool_calls
                tool_calls = message.get('tool_calls', [])

                if not tool_calls:
                    # 没有 tool_calls，直接显示回复
                    assistant_reply = message.get('content', '')
                    if assistant_reply:
                        messages.append(message)
                        if use_stream:
                            # 流式模式：内容已在实时输出中打印，补换行
                            print()
                        else:
                            print_msg("\n  " + "\u2500" * 58, 'green')
                            print(strip_markdown(assistant_reply))
                            print_msg("  " + "\u2500" * 58, 'green')
                    break

                # 有 tool_calls，需要处理
                messages.append(message)

                for tool_call in tool_calls:
                    func_name = tool_call['function']['name']
                    func_args = json.loads(tool_call['function']['arguments'])

                    if func_name == 'run_command':
                        detail = func_args.get('command', '')
                    elif func_name == 'read_file':
                        detail = func_args.get('filepath', '')
                    elif func_name == 'list_directory':
                        detail = func_args.get('path', '.')
                    else:
                        detail = ''
                    if detail:
                        print_msg("\n  [{}] {}".format(func_name, detail), 'yellow')
                    else:
                        print_msg("\n  [{}]".format(func_name), 'yellow')

                    # 执行工具
                    tool_result = execute_tool(func_name, func_args)

                    # 添加工具结果（智能截断）
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "content": truncate_output(tool_result)
                    })

                    # 终端显示（较短截断）
                    print_msg("  " + "\u2500" * 58, 'white')
                    display_text = tool_result[:MAX_DISPLAY_CHARS]
                    if len(tool_result) > MAX_DISPLAY_CHARS:
                        display_text += "\n...(结果过长，终端已截断，完整内容已送给 LLM)"
                    print(display_text)

                    # 继续循环，让 LLM 基于工具结果生成回复

        except KeyboardInterrupt:
            print_info("\n再见!")
            break
        except Exception as e:
            print_error("发生错误: " + str(e))
            if ARGS.debug:
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    main()
