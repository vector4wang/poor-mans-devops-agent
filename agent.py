#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Poor Man's DevOps Agent - 乞丐版运维助手
Poor Man's DevOps Agent - A lightweight production debugging assistant

支持 Python 2.7+ 和 Python 3.x

使用方法（配置优先级：命令行参数 > 环境变量 > 引导式输入）:
    # 方式一：引导式填值（运行时逐项输入）
    python agent.py

    # 方式二：命令行参数传值（非交互，适合自动化 / CI）
    python agent.py --api-url https://your-api-url/v1/chat/completions \
                    --api-key your-api-key --model gpt-4o

    # 方式三：设置环境变量
    export DEBUGBOT_API_URL="https://your-api-url/v1/chat/completions"
    export DEBUGBOT_API_KEY="your-api-key"
    export DEBUGBOT_MODEL="gpt-4o"
    python agent.py

    # 参数不全时，缺失项会自动回落到环境变量，再回落到引导式输入；
    # 加 --non-interactive 可在配置不全时直接报错，不等待输入。
"""

from __future__ import print_function, absolute_import

import argparse
import io
import os
import sys
import json
import subprocess
import re
import time
import ssl
import platform

# Python 2/3 兼容
PY2 = sys.version_info[0] == 2

if PY2:
    input = raw_input
    from urllib2 import Request, urlopen, HTTPError, URLError
else:
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError

# ============== 配置区 ==============
# 配置占位符（环境变量等于此值时视为未设置，需要引导填写）
PLACEHOLDER_API_URL = 'https://your-api-url/v1/chat/completions'

API_URL = os.environ.get('DEBUGBOT_API_URL', PLACEHOLDER_API_URL)
API_KEY = os.environ.get('DEBUGBOT_API_KEY', 'your-api-key')
MODEL = os.environ.get('DEBUGBOT_MODEL', 'gpt-4o')

# 调试模式开关（由 --debug 参数开启）
DEBUG = False

# 流式输出开关（由 --no-stream / DEBUGBOT_STREAM 控制；setup_config 中解析）
STREAM_ENABLED = True

# ============== 工作区（记忆 + 临时脚本）==============
# 工作区位于 agent.py 所在目录下的 debugbot-workspace/，固定复用以让记忆跨会话累积。
# 可用环境变量 DEBUGBOT_WORKSPACE 覆盖到任意路径。
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.environ.get('DEBUGBOT_WORKSPACE', os.path.join(AGENT_DIR, 'debugbot-workspace'))
MEMORY_DIR = os.path.join(WORKSPACE_DIR, 'memories')          # 跨会话记忆（Claude Code 风格 frontmatter）
MEMORY_INDEX = os.path.join(MEMORY_DIR, 'MEMORY.md')          # 记忆索引（每条一行）
SCRIPT_DIR = os.path.join(WORKSPACE_DIR, 'scripts')            # 临时脚本根目录
# 本次会话的脚本子目录（按时间戳隔离，避免不同会话脚本互相覆盖）
SESSION_STAMP = time.strftime('%Y%m%d_%H%M%S')
SESSION_SCRIPT_DIR = os.path.join(SCRIPT_DIR, SESSION_STAMP)

# TodoWrite 任务列表（会话级内存）
TODOS = []

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
COMPACT_THRESHOLD = 30       # 触发摘要压缩的消息条数阈值
KEEP_RECENT = 12             # 压缩时保留的最近消息条数（软目标，_safe_recent 可能更少）

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

# ============== 终端输出渲染 ==============

def render_line(line, in_code):
    """把单行 Markdown 渲染成终端友好的纯文本（代码块感知）。

    in_code 为当前是否处于代码块内。返回 (rendered_line, new_in_code)。
    代码块内原样保留（命令/输出不能被改写）；块外把 # 标题转成分隔线标题、
    **粗体**/`代码` 去掉包裹符、无序列表 -/* 转成 •。
    """
    stripped = line.strip()

    # 代码块围栏 ``` 或 ~~~：翻转状态，输出分隔线（去掉语言标记）
    if stripped.startswith('```') or stripped.startswith('~~~'):
        return '  ' + '─' * 40, (not in_code)

    if in_code:
        # 代码块内：原样保留
        return line, True

    # 块外：标题 # / ## / ... -> 分隔线标题
    m = re.match(r'^(#{1,6})\s+(.*)$', line)
    if m:
        title = m.group(2).strip()
        title = re.sub(r'\*\*(.+?)\*\*', r'\1', title)
        title = re.sub(r'`([^`]+)`', r'\1', title)
        pad = max(2, 40 - 4 - len(title))   # '── ' + title + ' ' + 分隔
        return '── ' + title + ' ' + '─' * pad, False

    # 块外：行内清理 + 无序列表
    out = line
    out = re.sub(r'\*\*(.+?)\*\*', r'\1', out)
    out = re.sub(r'`([^`]+)`', r'\1', out)
    out = re.sub(r'^(\s*)[-*+]\s+', r'\1• ', out)
    return out, False

def render_block(text):
    """把整段 Markdown 渲染成终端友好文本（代码块感知），用于非流式输出。"""
    lines = text.split('\n')
    in_code = False
    out = []
    for line in lines:
        rendered, in_code = render_line(line, in_code)
        out.append(rendered)
    return '\n'.join(out)

# ============== 上下文压缩 ==============

def _safe_recent(messages, keep):
    """从 messages 末尾取 keep 条作为最近窗口，前向越过开头的 orphan role='tool' 消息。

    OpenAI API 要求每个 tool 消息都有对应的 assistant tool_call；若最近窗口以一条
    tool 消息开头（其发起的 assistant 已被淘汰），下一个请求会被 400 拒绝。
    前向越过这些 tool 消息（连同其发起的 assistant 整组）一并移入淘汰集，使两侧都不留孤儿。

    返回 (recent_list, cut_index)；cut 永不触碰 messages[0]（system prompt）。
    """
    n = len(messages)
    cut = max(1, n - keep)
    while cut < n and messages[cut].get('role') == 'tool':
        cut += 1
    return messages[cut:], cut

def _crude_compact(messages):
    """简单截断回退：保留 system + 摘要占位 + 最近窗口（走 _safe_recent 保证 API 合法）。

    当 LLM 摘要调用失败时使用，避免硬崩。
    """
    recent, cut = _safe_recent(messages, KEEP_RECENT)
    system_msg = messages[0]
    del messages[:]
    messages.append(system_msg)
    messages.append({
        "role": "user",
        "content": "[系统提示: 之前的对话轮次过多，已自动压缩。请基于当前上下文继续排查]"
    })
    messages.extend(recent)
    print_warn("已回退为简单压缩上下文（保留最近 {} 条消息）".format(len(recent)))

def compact_messages(messages):
    """超过 COMPACT_THRESHOLD 时，把被淘汰的中间消息送 LLM 出摘要并替换，保留最近窗口。

    任意失败（HTTP/空 choices/空 content/异常）→ _crude_compact 回退，永不硬崩。
    原地修改 messages：messages[0]（system）不动，其后插入一条摘要 user 消息，再接最近窗口。
    """
    if len(messages) <= COMPACT_THRESHOLD:
        return

    recent, cut = _safe_recent(messages, KEEP_RECENT)
    evicted = messages[1:cut]   # 开头非 tool、末尾是完整 tool 组（或普通消息），API 合法

    summary_prompt = ("你是对话压缩助手。请将以下运维排查对话压缩为简洁摘要，"
                      "保留：关键发现、涉及的文件/命令、当前任务与未决问题。"
                      "用要点形式，控制在 500 字以内。")
    summary_messages = [{"role": "system", "content": summary_prompt}] + evicted

    summary = ''
    try:
        result, error = call_llm(summary_messages, tools=None, stream=False)
        if error or not result or not result.get('choices'):
            raise RuntimeError(error or "空 choices")
        summary = (result['choices'][0].get('message', {}) or {}).get('content', '') or ''
        if not summary.strip():
            raise RuntimeError("空摘要")
    except Exception as e:
        print_warn("摘要压缩失败（{}），回退简单截断".format(str(e)[:80]))
        _crude_compact(messages)
        return

    system_msg = messages[0]
    del messages[:]
    messages.append(system_msg)
    messages.append({"role": "user", "content": "[上下文摘要]\n" + summary.strip()})
    messages.extend(recent)
    print_warn("对话轮次过多，已用 LLM 摘要压缩上下文（保留最近 {} 条消息 + 摘要）".format(len(recent)))

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
    print_msg("[WARN] " + msg, 'yellow')

def print_info(msg):
    print_msg("[INFO] " + msg, 'cyan')

def print_success(msg):
    print_msg("[OK] " + msg, 'green')

def _safe_write(text):
    """流式逐块写入 stdout，兼容 cp936 等 GBK 系控制台，避免 UnicodeEncodeError 崩流。

    Py3 优先走 sys.stdout.buffer 写字节；Py2 无 .buffer 时回退为 encode/decode round-trip。
    """
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, 'encoding', 'utf-8') or 'utf-8'
        buf = getattr(sys.stdout, 'buffer', None)
        if buf is not None:
            try:
                buf.write(text.encode(enc, 'replace'))
                buf.flush()
                return
            except (IOError, OSError):
                pass
        # Py2 无 buffer 的最终回退：round-trip 替换不可编码字符
        try:
            sys.stdout.write(text.encode(enc, 'replace').decode(enc, 'replace'))
            sys.stdout.flush()
        except Exception:
            pass

def is_path_allowed(path):
    """检查路径是否在允许范围内"""
    if not path:
        return False

    # 工作区内的文件（记忆、脚本）一律允许读
    ws_full = resolve_workspace_path(path)
    if ws_full is not None:
        return True

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

def is_dangerous_command(cmd):
    """检查是否是危险命令"""
    if not cmd:
        return True
    cmd = cmd.strip()
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, cmd):
            return True
    return False

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

        with io.open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
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
        if PY2:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE
            )
            stdout, stderr = process.communicate(timeout=timeout)
        else:
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
    print()  # 空行
    print_msg("=" * 60, 'yellow')
    print_msg("[{}] 需要执行以下操作:".format(tool_name), 'yellow')
    print_msg("=" * 60, 'yellow')
    print_msg(cmd, 'white')
    print_msg("=" * 60, 'yellow')
    print()  # 空行

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

def _consume_stream(response):
    """消费 SSE 流式响应。

    逐块把 delta.content 打到终端（打字机效果），按 index 增量拼装 delta.tool_calls，
    返回与非流式响应同形的 dict：{"choices":[{"message":{"role","content","tool_calls"?},"finish_reason"}]}
    以便主循环无需感知流式差异。

    首 token 之后若出错，返回 (None, err)（已打印内容无法撤回，不能重试）。
    """
    content_acc = []          # 正文片段列表
    tools_acc = {}            # index -> {id, type, name, arguments}
    finish_reason = None
    header_done = False
    content_pending = ['']    # 跨 chunk 的未完成行（行缓冲渲染用）
    in_code = [False]        # 当前是否在代码块内（跨行状态，用 list 包以便闭包修改）

    try:
        while True:
            raw = response.readline()
            if not raw:          # EOF（空 b''）——与空行 keepalive（b'\n'）区分：先判 raw 再 decode
                break
            line = raw.decode('utf-8', errors='replace')
            s = line.strip()
            if not s:            # 空行/分隔符
                continue
            if s.startswith(':'):   # SSE 注释/心跳
                continue
            if not s.startswith('data:'):
                continue
            payload_str = s[5:].lstrip()
            if payload_str == '[DONE]':
                break
            try:
                chunk = json.loads(payload_str)
            except ValueError:
                continue

            choices = chunk.get('choices') or [{}]
            choice = choices[0]
            delta = choice.get('delta', {}) or {}
            fr = choice.get('finish_reason')
            if fr:
                finish_reason = fr

            # 正文增量（按行缓冲渲染：遇 \n 才渲染整行，保留打字机效果且能做代码块感知的格式化）
            c = delta.get('content')
            if c:
                if not header_done:
                    print_msg("\n[助手]", 'green')
                    header_done = True
                content_acc.append(c)
                content_pending[0] += c
                while '\n' in content_pending[0]:
                    line, content_pending[0] = content_pending[0].split('\n', 1)
                    rendered, in_code[0] = render_line(line, in_code[0])
                    _safe_write(rendered + '\n')

            # tool_calls 增量拼装（按 index）
            tcs = delta.get('tool_calls')
            if tcs:
                for tc in tcs:
                    idx = tc.get('index', 0)
                    entry = tools_acc.get(idx)
                    if entry is None:
                        entry = {'id': None, 'type': None, 'name': None, 'arguments': ''}
                        tools_acc[idx] = entry
                    if 'id' in tc and tc['id']:
                        entry['id'] = tc['id']
                    if 'type' in tc and tc['type']:
                        entry['type'] = tc['type']
                    fn = tc.get('function') or {}
                    if fn.get('name'):
                        entry['name'] = fn['name']
                    if 'arguments' in fn and fn['arguments']:
                        entry['arguments'] += fn['arguments']

        # 收尾：渲染缓冲里残留的最后一行（末尾无换行的情况）
        if content_pending[0]:
            rendered, in_code[0] = render_line(content_pending[0], in_code[0])
            _safe_write(rendered)
            content_pending[0] = ''

        # 收尾换行
        if header_done:
            _safe_write("\n")

    except Exception as e:
        # 已开始打印后的异常：尽量返回已拼好的部分，避免硬崩
        return None, "流式响应中断: " + str(e)

    # 仅在 finish_reason == 'tool_calls' 时认为 tool_calls 完整；否则丢弃不完整片段
    # （防止主循环对残缺 arguments 做 json.loads 报错）
    tool_calls_complete = (finish_reason == 'tool_calls')

    content_text = ''.join(content_acc) if content_acc else ''

    message = {'role': 'assistant', 'content': content_text if content_text else None}
    if tool_calls_complete and tools_acc:
        ordered = [tools_acc[i] for i in sorted(tools_acc.keys())]
        message['tool_calls'] = [
            {
                'id': e['id'] or ('call_{}'.format(i)),
                'type': e['type'] or 'function',
                'function': {'name': e['name'] or '', 'arguments': e['arguments'] or '{}'},
            }
            for i, e in enumerate(ordered)
        ]

    assembled = {
        'choices': [{
            'index': 0,
            'message': message,
            'finish_reason': finish_reason or 'stop',
        }]
    }
    return assembled, None

def call_llm(messages, tools=None, stream=None):
    """调用 LLM API。stream=None 时取全局 STREAM_ENABLED。

    流式时逐块打印正文（打字机效果）并增量拼装 tool_calls，返回与非流式同形的
    response dict，使主循环无需感知流式/非流式差异。
    """
    if stream is None:
        stream = STREAM_ENABLED

    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + API_KEY
    }

    payload = {
        'model': MODEL,
        'messages': messages,
        'temperature': 0.7,
    }

    # DeepSeek 特殊参数：禁用思考模式
    if 'deepseek' in API_URL.lower():
        payload['thinking'] = {"type": "disabled"}

    # 调试模式：打印发送的消息
    if DEBUG:
        print_msg("\n[DEBUG] 发送的消息:", 'magenta')
        for i, msg in enumerate(messages):
            role = msg.get('role')
            tc = msg.get('tool_calls')
            print_msg("  [{}] role={}, has_tool_calls={}".format(i, role, bool(tc)), 'white')
            if tc:
                for t in tc:
                    print_msg("      -> id={}, func={}".format(t.get('id'), t['function']['name']), 'white')
            if role == 'tool':
                print_msg("      -> tool_call_id={}, content_len={}".format(msg.get('tool_call_id'), len(msg.get('content', ''))), 'white')

    if tools:
        payload['tools'] = tools

    if stream:
        payload['stream'] = True

    if PY2:
        data = json.dumps(payload)
    else:
        data = json.dumps(payload).encode('utf-8')

    # 重试机制
    max_retries = 3
    for attempt in range(max_retries):
        try:
            req = Request(API_URL, data=data, headers=headers)

            # Python 3: 更好的 SSL 配置
            if not PY2:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                response = urlopen(req, timeout=120, context=ssl_context)
            else:
                response = urlopen(req, timeout=120)

            if stream:
                # 流式：逐块打印正文 + 增量拼装 tool_calls；返回与非流式同形的 dict。
                # 首字节前若连接异常会被下面的 except 捕获并重试；
                # 已开始打印后的异常 _consume_stream 返回 (None, err)（无法撤回已打印内容，不重试）。
                assembled, serr = _consume_stream(response)
                if serr is not None:
                    return None, serr
                return assembled, None

            if PY2:
                result = response.read().decode('utf-8')
            else:
                result = response.read().decode('utf-8')

            return json.loads(result), None

        except HTTPError as e:
            error_body = e.read().decode('utf-8') if hasattr(e, 'read') else ''
            return None, "HTTP Error {}: {}".format(e.code, error_body)
        except URLError as e:
            if attempt < max_retries - 1:
                print_warn("连接失败，{} 秒后重试... ({}/{})".format(2 ** attempt, attempt + 1, max_retries))
                import time
                time.sleep(2 ** attempt)
                continue
            return None, "URL Error: " + str(e.reason)
        except Exception as e:
            if attempt < max_retries - 1:
                print_warn("请求失败，重试中... ({}/{})".format(attempt + 1, max_retries))
                import time
                time.sleep(2 ** attempt)
                continue
            return None, "Error: " + str(e)

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
                "name": "todo_write",
                "description": "更新任务列表。在多步排查（≥3 步）开始时列出计划，每完成一步更新状态，便于跟踪进度。一次传入完整列表（含未完成项）。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "todos": {
                            "type": "array",
                            "description": "任务列表（覆盖式更新）",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "content": {"type": "string", "description": "任务描述"},
                                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed"], "description": "任务状态"},
                                    "activeForm": {"type": "string", "description": "进行中时的描述（如 正在查看内存）"}
                                },
                                "required": ["content", "status"]
                            }
                        }
                    },
                    "required": ["todos"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "写文件到工作区（持久化记忆或临时脚本）。path 相对工作区根目录。写 memories/*.md 会自动维护 MEMORY.md 索引——记忆请带 frontmatter(name/description/type)。脚本建议放 scripts/ 会话目录。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "相对工作区的路径，如 memories/oom-threshold.md 或 scripts/probe.py"
                        },
                        "content": {
                            "type": "string",
                            "description": "文件内容"
                        }
                    },
                    "required": ["path", "content"]
                }
            }
        }
    ]

def execute_tool(tool_name, tool_input, dry_run=False):
    """执行工具"""
    if tool_name == "read_file":
        filepath = tool_input.get("filepath", "")
        if dry_run:
            return "[Dry Run] 将读取文件: " + filepath

        content, error = safe_read_file(filepath)
        if error:
            return "读取文件失败: " + error
        return content if content else "[空文件]"

    elif tool_name == "run_command":
        command = tool_input.get("command", "")
        if dry_run:
            return "[Dry Run] 将执行命令: " + command

        # 检查命令是否在白名单中
        allowed, reason = is_command_allowed(command)

        if allowed == False:
            # 危险命令，直接拒绝
            return "命令不允许: " + reason

        # 安全只读命令直接执行
        if is_safe_readonly_command(command):
            print_msg("[执行] " + command, 'blue')
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
        if dry_run:
            return "[Dry Run] 将列出目录: " + path

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
        if dry_run:
            return "[Dry Run] 将收集环境快照"
        return run_env_snapshot(include_proc, include_net)

    elif tool_name == "todo_write":
        todos = tool_input.get("todos", [])
        if dry_run:
            return "[Dry Run] 将更新任务列表: {} 项".format(len(todos))
        return update_todos(todos)

    elif tool_name == "write_file":
        path = (tool_input.get("path") or "").strip()
        content = tool_input.get("content", "")
        if dry_run:
            return "[Dry Run] 将写入文件: " + path
        return write_workspace_file(path, content)

    return "[未知工具: {}]".format(tool_name)

def write_workspace_file(path, content):
    """写文件到工作区。path 相对工作区根；越界拒绝。memories/*.md 自动维护 MEMORY.md 索引。

    返回人类可读的结果串（含写入的绝对路径，便于 LLM 后续 read_file / run_command 引用）。
    """
    if not path:
        return "写入失败: path 为空"
    full = resolve_workspace_path(path)
    if full is None:
        return "写入失败: 路径越出工作区范围: {}".format(path)
    try:
        parent = os.path.dirname(full)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with io.open(full, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        return "写入失败: " + str(e)

    # memories/ 下的 .md 维护索引
    norm = full.replace('\\', '/')
    if '/memories/' in norm and full.endswith('.md') and not full.endswith('MEMORY.md'):
        meta, _ = parse_frontmatter(content)
        update_memory_index(full, meta)

    print_msg("[写入] " + full, 'blue')
    return "已写入: {}（{} 字节）".format(full, len(content))

def update_todos(todos):
    """覆盖式更新全局任务列表并渲染。"""
    global TODOS
    cleaned = []
    for item in todos or []:
        if not isinstance(item, dict):
            continue
        content = (item.get('content') or '').strip()
        if not content:
            continue
        status = item.get('status') or 'pending'
        if status not in ('pending', 'in_progress', 'completed'):
            status = 'pending'
        cleaned.append({
            'content': content,
            'status': status,
            'activeForm': (item.get('activeForm') or content).strip(),
        })
    TODOS = cleaned
    print_todos()
    return "已更新任务列表（共 {} 项）".format(len(cleaned))

def print_todos():
    """彩色渲染当前任务列表。"""
    if not TODOS:
        print_msg("\n[任务列表] （空）", 'yellow')
        return
    print_msg("\n[任务列表]", 'yellow')
    for t in TODOS:
        status = t.get('status', 'pending')
        if status == 'completed':
            mark, color = '[x]', 'green'
        elif status == 'in_progress':
            mark, color = '[..]', 'cyan'
        else:
            mark, color = '[ ]', 'white'
        print_msg("  {} {}".format(mark, t.get('activeForm') or t.get('content', '')), color)

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

def resolve_value(cli_val, env_val, placeholder=None):
    """按 命令行参数 > 环境变量 解析单个配置项，剔除占位默认值。

    返回 (value, source)：source 为 'CLI' / 'env' / None
    （None 表示该项未提供，需要引导填写）。
    """
    if cli_val:
        return cli_val, 'CLI'
    if env_val and (placeholder is None or env_val != placeholder):
        return env_val, 'env'
    return '', None


def parse_args(argv=None):
    """解析命令行参数。

    未提供的配置项会按 环境变量 > 引导式输入 的顺序补全，
    真正的合并与交互在 setup_config() 中完成。
    """
    parser = argparse.ArgumentParser(
        description="Poor Man's DevOps Agent - 乞丐版运维助手（支持参数传值与引导式填值）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
配置优先级：命令行参数 > 环境变量 > 引导式输入

示例:
  # 1) 引导式填值（交互逐项输入）
  python agent.py

  # 2) 参数传值（非交互，适合自动化 / CI）
  python agent.py --api-url https://your-llm/v1/chat/completions \\
                  --api-key sk-xxxxx --model deepseek-chat

  # 3) 混合：部分参数 + 环境变量补全缺失项
  python agent.py --model gpt-4o

  # 4) 仅用环境变量
  DEBUGBOT_API_URL=... DEBUGBOT_API_KEY=... python agent.py

  # 5) 非交互模式：配置不全直接报错，不等待输入
  python agent.py --api-url ... --api-key ... --non-interactive

环境变量:
  DEBUGBOT_API_URL   LLM API 地址
  DEBUGBOT_API_KEY   API Key
  DEBUGBOT_MODEL     模型名称（默认 gpt-4o）
""")
    parser.add_argument('-u', '--api-url', default=None,
                        help='LLM API 地址（环境变量 DEBUGBOT_API_URL）')
    parser.add_argument('-k', '--api-key', default=None,
                        help='API Key（环境变量 DEBUGBOT_API_KEY）')
    parser.add_argument('-m', '--model', default=None,
                        help='模型名称（环境变量 DEBUGBOT_MODEL，默认 gpt-4o）')
    parser.add_argument('-n', '--non-interactive', action='store_true', default=False,
                        help='非交互模式：配置不全时直接报错退出，不进入引导式填写')
    parser.add_argument('--debug', action='store_true', default=False,
                        help='调试模式：打印发送给 LLM 的消息')
    parser.add_argument('--no-stream', dest='no_stream', action='store_true', default=False,
                        help='禁用流式输出（某些端点不支持流式；亦可用 DEBUGBOT_STREAM=0）')
    return parser.parse_args(argv)


def setup_config(args):
    """运行时配置。

    优先级：命令行参数 > 环境变量 > 引导式输入
    - url/key 通过参数或环境变量齐全时，不进行任何交互（适合自动化）
    - 有缺失且未指定 --non-interactive 时，仅引导填写缺失项
    """
    global API_URL, API_KEY, MODEL, DEBUG, STREAM_ENABLED

    DEBUG = bool(getattr(args, 'debug', False))

    # 流式开关优先级：--no-stream > DEBUGBOT_STREAM 环境变量 > 默认 True
    if getattr(args, 'no_stream', False):
        STREAM_ENABLED = False
    else:
        ev = os.environ.get('DEBUGBOT_STREAM', '').strip().lower()
        STREAM_ENABLED = (not ev) or (ev not in ('0', 'false', 'no', 'off'))

    print_msg("""
     ██████╗ ██████╗ ███████╗███╗   ███╗██╗███╗   ██╗ ██████╗ ██╗     ██╗████████╗██╗ ██████╗ ███╗   ██╗
    ██╔══██╗██╔══██╗██╔════╝████╗ ████║██║████╗  ██║██╔════╝ ██║     ██║╚══██╔══╝██║██╔═══██╗████╗  ██║
    ██████╔╝██████╔╝███████╗██╔████╔██║██║██╔██╗ ██║██║  ███╗██║     ██║   ██║   ██║██║   ██║██╔██╗ ██║
    ██╔═══╝ ██╔══██╗╚════██║██║╚██╔╝██║██║██║╚██╗██║██║   ██║██║     ██║   ██║   ██║██║   ██║██║╚██╗██║
    ██║     ██║  ██║███████║██║ ╚═╝ ██║██║██║ ╚████║╚██████╔╝███████╗██║   ██║   ██║╚██████╔╝██║ ╚████║
    ╚═╝     ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝

                                      ███████╗██████╗  ██████╗ ███████╗███████╗██╗██╗  ██╗   ██╗
                                      ██╔════╝██╔══██╗██╔═══██╗██╔════╝██╔════╝██║██║  ██║   ██║
                                      █████╗  ██████╔╝██║   ██║███████╗█████╗  ██║██║  ██║██╗██║
                                      ██╔══╝  ██╔══██╗██║   ██║╚════██║██╔══╝  ██║██║  ██║╚████╔╝
                                      ██║     ██║  ██║╚██████╔╝███████║███████╗██║╚█████╔╝ ╚██╔╝
                                      ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝╚═╝ ╚════╝   ╚═╝
    """, 'cyan')

    print_msg("  >> Poor Man's DevOps Agent <<", 'yellow')
    print_msg("  >> AI-Powered | Command Whitelist | Human-in-the-Loop <<", 'white')
    print()
    print_msg("  [ Supported ]", 'green')
    print_msg("  ├─ System   : ps, top, free, df, du, uptime", 'white')
    print_msg("  ├─ Network  : curl, ping, netstat, ss, dig", 'white')
    print_msg("  ├─ Docker   : ps, logs, inspect, stats, exec", 'white')
    print_msg("  ├─ K8s      : get, describe, logs, top", 'white')
    print_msg("  ├─ Database : MySQL, PostgreSQL, Redis (read-only)", 'white')
    print_msg("  └─ Snapshot : env_snapshot (一键环境快照)", 'white')
    print()

    # 配置优先级：命令行参数 > 环境变量 > 引导式输入
    url, url_src = resolve_value(args.api_url,
                                 os.environ.get('DEBUGBOT_API_URL', ''),
                                 PLACEHOLDER_API_URL)
    key, key_src = resolve_value(args.api_key,
                                 os.environ.get('DEBUGBOT_API_KEY', ''))
    model = args.model or os.environ.get('DEBUGBOT_MODEL', '')
    model_src = 'CLI' if args.model else ('env' if os.environ.get('DEBUGBOT_MODEL', '') else None)

    # 引导式填值：仅补全缺失的必填项（url / key）
    if (not url) or (not key):
        if args.non_interactive:
            print_error("非交互模式下配置不完整：缺少 API URL 或 API Key。")
            print_info("请通过 --api-url / --api-key 传入，或设置环境变量 "
                       "DEBUGBOT_API_URL / DEBUGBOT_API_KEY 后重试。")
            sys.exit(1)

        print_info("[ Config ] 检测到配置不完整，进入引导式填写"
                   "（也可改用 --api-url / --api-key / --model 参数传入）")
        print()
        if not url:
            print_msg("  API Endpoint: ", 'white')
            url = input().strip()
            url_src = 'input'
        if not key:
            print_msg("  API Key    : ", 'white')
            key = input().strip()
            key_src = 'input'
        if not model:
            print_msg("  Model      : (回车默认 gpt-4o) ", 'white')
            model = input().strip() or 'gpt-4o'
            model_src = 'input'

    if not model:
        model = 'gpt-4o'
        model_src = model_src or 'default'

    API_URL = url
    API_KEY = key
    MODEL = model

    if not API_URL or not API_KEY:
        print_error("API URL 和 API Key 不能为空!")
        sys.exit(1)

    src_label = {
        'CLI': '命令行参数',
        'env': '环境变量',
        'input': '引导输入',
        'default': '默认值',
        None: '默认值',
    }

    # 初始化工作区目录（记忆 + 本次会话脚本）
    ensure_workspace()

    print()
    print_msg("  [ Status ]", 'green')
    print_msg("  ├─ Endpoint : {} ({})".format(API_URL, src_label.get(url_src, url_src)), 'white')
    print_msg("  ├─ Model    : {} ({})".format(MODEL, src_label.get(model_src, model_src)), 'white')
    print_msg("  ├─ Stream   : {} (--no-stream 关闭)".format('ENABLED' if STREAM_ENABLED else 'DISABLED'), 'white')
    print_msg("  ├─ Workspace: {}".format(WORKSPACE_DIR), 'white')
    print_msg("  ├─ Safe Mode: ENABLED (whitelist + human approval)", 'yellow')
    print_msg("  └─ Allowed  : /home, /var/log, /etc, /tmp, /app, workspace/...")
    print()
    print_msg("  quit/exit 退出 | /help 命令 | 多行以 \"\"\" 开始并以单独一行 \"\"\" 结束", 'cyan')
    print()

def read_user_input():
    """读取用户输入，支持多行粘贴。

    - 单行：直接输入并回车即发送（保持原有行为）。
    - 多行：第一行单独输入 \"\"\"（或 '''）进入多行模式，随后可粘贴任意
      内容（日志、堆栈、配置等，中间的空行会被保留），再次单独输入同样的
      引号结束，整段内容作为一条消息发送。

    这样可避免粘贴多行内容时被逐行拆成多条输入（input() 只读到第一个换行）。
    返回去除首尾空白后的文本。
    """
    print("[你]")
    first = input()
    line = first.strip()

    if line in ('"""', "'''"):
        quote = line
        print_msg("  [多行模式] 粘贴内容后，以单独一行 {} 结束（Ctrl-C 取消）".format(quote), 'cyan')
        lines = []
        while True:
            try:
                chunk = input()
            except (KeyboardInterrupt, EOFError):
                print_info("  [已取消多行输入]")
                return ''
            if chunk.strip() == quote:
                break
            lines.append(chunk)
        return '\n'.join(lines).strip()

    return line


def git_info():
    """best-effort 采集 git 分支与未提交变更数；非 git 仓库或失败返回空串。"""
    try:
        def run(cmd):
            p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, cwd=os.getcwd())
            out, _ = p.communicate(timeout=5)
            return out.decode('utf-8', errors='ignore').strip()
        branch = run("git rev-parse --abbrev-ref HEAD")
        if not branch:
            return ''
        dirty = run("git status --porcelain 2>/dev/null | wc -l")
        parts = ["git 分支: {}".format(branch)]
        if dirty:
            parts.append("未提交变更: {} 项".format(dirty))
        return " | ".join(parts)
    except Exception:
        return ''


def ensure_workspace():
    """best-effort 创建工作区目录结构（memories/ + scripts/会话子目录）。失败不阻塞启动。"""
    try:
        for d in (MEMORY_DIR, SCRIPT_DIR, SESSION_SCRIPT_DIR):
            if not os.path.isdir(d):
                os.makedirs(d)
    except Exception:
        pass


def parse_frontmatter(text):
    """解析简单的 YAML frontmatter（--- 之间的 name/description/type 等键值），零依赖。

    返回 (meta_dict, body)。不处理嵌套；支持 metadata.type 的扁平读法。
    """
    meta = {}
    body = text
    t = text.lstrip('\n')
    if not t.startswith('---'):
        return meta, body
    rest = t[3:]
    nl = rest.find('\n')
    if nl < 0:
        return meta, body
    fm = rest[nl + 1:]
    end = fm.find('\n---')
    if end < 0:
        return meta, body
    fm_block = fm[:end]
    body = fm[end + 4:].lstrip('\n')
    in_metadata = False
    for line in fm_block.split('\n'):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if s == 'metadata:':
            in_metadata = True
            continue
        if line and not line.startswith(' ') and not line.startswith('\t'):
            in_metadata = False
        if ':' in s:
            k, v = s.split(':', 1)
            meta[k.strip()] = v.strip()
    return meta, body


def resolve_workspace_path(path):
    """把相对工作区的 path 解析为绝对路径，并校验落在工作区内（防 ../ 逃逸）。

    path 也可为绝对路径（必须已在工作区内）。返回绝对路径或 None（越界）。
    """
    if os.path.isabs(path):
        full = os.path.normpath(path)
    else:
        full = os.path.normpath(os.path.join(WORKSPACE_DIR, path))
    ws = os.path.abspath(WORKSPACE_DIR)
    if full == ws or full.startswith(ws + os.sep):
        return full
    return None


def update_memory_index(filepath, meta):
    """写 memories/ 下的记忆后，更新 MEMORY.md 索引（每条一行，去重替换）。

    索引行格式：- name: description (filename)
    """
    try:
        filename = os.path.basename(filepath)
        name = meta.get('name') or os.path.splitext(filename)[0]
        desc = meta.get('description', '')
        new_line = "- {}: {} ({})".format(name, desc, filename)

        lines = []
        if os.path.exists(MEMORY_INDEX):
            with io.open(MEMORY_INDEX, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [ln.rstrip('\n') for ln in f.readlines()]
        # 去掉指向同一文件的旧条目
        kept = [ln for ln in lines if not ln.strip().endswith('(' + filename + ')')]
        kept.append(new_line)
        with io.open(MEMORY_INDEX, 'w', encoding='utf-8') as f:
            f.write('\n'.join(kept) + '\n')
    except Exception:
        pass


def load_memory():
    """读取 MEMORY.md 索引拼进系统提示（progressive disclosure：只载索引，具体内容 LLM 用 read_file 按需读）。

    不存在或失败返回空串。
    """
    try:
        if not os.path.exists(MEMORY_INDEX):
            return ''
        with io.open(MEMORY_INDEX, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read().strip()
    except Exception:
        return ''


SLASH_HELP = """可用斜杠命令：
  /help      显示本帮助
  /quit      退出（等同 quit / exit）
  /clear     清空对话历史，仅保留系统提示
  /compact   立即压缩当前上下文（LLM 摘要）
  /snapshot  一键采集环境快照
  /todo      查看当前任务列表
  /tools     列出可用工具
  /workspace 显示工作区目录与记忆索引
多行输入：以单独一行 \"\"\" 开始，再以单独一行 \"\"\" 结束。"""


def handle_slash_command(text, messages):
    """处理以 / 开头的内建命令。

    返回状态：'none'（非命令，交给 LLM）/ 'handled'（已处理，继续主循环）/ 'quit'（退出）。
    """
    text = text.strip()
    if not text.startswith('/'):
        return 'none'
    parts = text.split(None, 1)
    cmd = parts[0].lower()

    if cmd in ('/help', '/?', '/h'):
        print_msg(SLASH_HELP, 'cyan')
        return 'handled'
    if cmd in ('/quit', '/exit', '/q'):
        print_info("再见!")
        print_warn("提醒：排查结束后建议删除 agent.py 避免 API Key 泄露：rm -f agent.py")
        return 'quit'
    if cmd == '/clear':
        system_msg = messages[0] if messages and messages[0].get('role') == 'system' else None
        del messages[:]
        if system_msg:
            messages.append(system_msg)
        else:
            messages.append({"role": "system", "content": ""})
        print_success("对话历史已清空（保留系统提示）")
        return 'handled'
    if cmd == '/compact':
        if len(messages) <= 1:
            print_info("对话过短，无需压缩")
        else:
            compact_messages(messages)
        return 'handled'
    if cmd == '/snapshot':
        print_msg("\n[环境快照]", 'cyan')
        print(run_env_snapshot(True, True))
        return 'handled'
    if cmd == '/todo':
        print_todos()
        return 'handled'
    if cmd == '/tools':
        print_msg("\n[可用工具]", 'cyan')
        for t in get_tools():
            fn = t['function']
            print_msg("  - {} : {}".format(fn['name'], fn.get('description', '').split('。')[0]), 'white')
        return 'handled'
    if cmd == '/workspace':
        print_msg("\n[工作区]", 'cyan')
        print_msg("  根目录   : {}".format(WORKSPACE_DIR), 'white')
        print_msg("  记忆目录 : {}".format(MEMORY_DIR), 'white')
        print_msg("  脚本目录 : {}".format(SESSION_SCRIPT_DIR), 'white')
        if os.path.exists(MEMORY_INDEX):
            print_msg("  记忆索引 :", 'white')
            print(load_memory())
        else:
            print_msg("  （尚无记忆）", 'white')
        return 'handled'

    print_warn("未知命令: {}（输入 /help 查看可用命令）".format(cmd))
    return 'handled'


def main():
    # 解析命令行参数（未提供的项会回落到环境变量，再回落到引导式输入）
    args = parse_args()

    # 运行时配置
    setup_config(args)

    # 系统提示 - 诊断方法论为核心，结构化短指令
    git = git_info()
    memory = load_memory()
    system_prompt = """你是 Poor Man's DevOps Agent（乞丐版运维助手），帮用户排查生产环境问题。
你是资深运维工程师，熟悉 Linux / Docker / Kubernetes / 各类中间件与数据库。

## 诊断方法论（核心）

排查 = 验证假设，不是跑命令。每个现象先在脑中形成 1-2 个最可能的原因（假设），
再用一条最小的只读命令去验证：命中就收敛深挖，未中就推翻换下一个假设。
始终清楚"我在验证哪个假设、还剩几个假设"，而非无目的堆命令。

标准循环：
1. 观察现象 → 2. 形成假设（1-2 个，按可能性排序）→ 3. 一条命令验证 →
   4a. 命中：收敛、继续定位根因  /  4b. 未中：换下一个假设，回到 2

例：服务慢。假设① GC 停顿 ② IO 瓶颈。先一条 ps/top 验证①——CPU/内存异常则深挖，
正常则一条 iostat 验证②。一条命令一个假设，不发散。

## 工具与诊断阶段

- env_snapshot : 建立全局认知。排查起点，一次看全系统状态，形成初始假设
- run_command  : 验证假设。用最小的只读命令验证某个假设（白名单校验 + 人工确认）
- read_file    : 看细节。读取日志、配置、代码、工作区记忆
- list_directory : 摸清结构
- todo_write   : 多步排查（≥3 步）时记录假设清单与验证进度，逐项推进
- write_file   : 沉淀结论。定位到根因/发现非显而易见的环境特征时，写入工作区记忆

## 安全铁律

绝对只读。绝不执行 rm、chmod、chown、kill 或任何修改数据的命令。
写文件只限工作区内（write_file 已做路径限制）。

## 输出格式

回复直接显示在终端，只输出纯文本，禁止任何 Markdown 符号。
- 标题：── 分析 ──────
- 列表：• 开头
- 命令：单独一行，前缀 $，如  $ docker stats
- 分段用空行

正例：
── 可能原因 ──────────
• GC 停顿（CPU 高时优先验证）
• IO 瓶颈
建议先跑：
  $ top
反例（禁止）：## 可能原因 / **CPU** / `docker stats` / | 表格 |

## 记忆与脚本

- 根因、服务架构、阈值、约定、踩过的坑 → write_file 写 memories/xxx.md，带 frontmatter：
  ---
  name: oom-threshold
  description: 该服务 OOM 阈值为内存 90%
  type: project
  ---
  正文。type 可为 project/feedback/reference/user。
- 探针/分析脚本 → write_file 写 scripts/ 会话目录，返回的绝对路径可直接 run_command 执行。

## 环境

- 工作目录: {cwd}
- 当前用户: {user}
- 平台: {plat} ({osname})
- Python 版本: {pyver}
- 工作区: {workspace}
  - 记忆: {memdir}（write_file 写入自动建索引；read_file 读具体记忆）
  - 脚本: {scriptdir}（本次会话）
{gitline}{memline}""".format(
        cwd=os.getcwd(),
        user=os.environ.get('USER', 'unknown'),
        plat=platform.platform(),
        osname=os.name,
        pyver=sys.version.split()[0],
        workspace=WORKSPACE_DIR,
        memdir=MEMORY_DIR,
        scriptdir=SESSION_SCRIPT_DIR,
        gitline=("- Git: " + git + "\n") if git else "",
        memline=("\n已有记忆索引（可用 read_file 读具体记忆 {memdir}/xxx.md）:\n{mem}\n".format(
                    memdir=MEMORY_DIR, mem=memory) if memory else "\n（尚无记忆；排查中如发现重要信息请用 write_file 沉淀）\n"),
    )

    messages = [
        {"role": "system", "content": system_prompt}
    ]

    tools = get_tools()

    while True:
        try:
            # 获取用户输入（支持多行粘贴：以 """ 包裹可粘贴整段内容）
            user_input = read_user_input()
        except (KeyboardInterrupt, EOFError):
            print_info("\n再见!")
            break

        if not user_input:
            continue

        # 斜杠命令（/help /clear /compact /snapshot /todo /tools /quit）
        if user_input.lstrip().startswith('/'):
            action = handle_slash_command(user_input, messages)
            if action == 'quit':
                break
            continue

        if user_input.lower() in ['quit', 'exit', 'q']:
            print_info("再见!")
            print_warn("提醒：排查结束后建议删除 agent.py 避免 API Key 泄露：rm -f agent.py")
            break

        try:
            # 添加用户消息
            messages.append({"role": "user", "content": user_input})

            # 主循环：处理可能的多次 tool_calls
            max_tool_rounds = 10  # 防止无限循环
            for round_num in range(max_tool_rounds):
                # 上下文压缩：超过阈值时用 LLM 摘要压缩（失败则回退简单截断）
                if len(messages) > COMPACT_THRESHOLD:
                    compact_messages(messages)

                # 调用 LLM
                print_msg("\n[思考中...]", 'magenta')

                result, error = call_llm(messages, tools)

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
                        # 流式已在生成时逐行渲染打印过 [助手]+正文；非流式在此整段渲染补打
                        if not STREAM_ENABLED:
                            print_msg("\n[助手]", 'green')
                            print(render_block(assistant_reply))
                    break

                # 有 tool_calls，需要处理
                messages.append(message)

                for tool_call in tool_calls:
                    func_name = tool_call['function']['name']
                    func_args = json.loads(tool_call['function']['arguments'])

                    print_msg("\n[调用工具: {}]".format(func_name), 'yellow')
                    if func_name == 'run_command':
                        print_msg("命令: " + func_args.get('command', ''), 'white')

                    # 执行工具
                    tool_result = execute_tool(func_name, func_args)

                    # 添加工具结果（智能截断）
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call['id'],
                        "content": truncate_output(tool_result)
                    })

                    # 终端显示（较短截断）
                    print_msg("\n[工具结果]", 'green')
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
            if DEBUG:
                import traceback
                traceback.print_exc()

if __name__ == '__main__':
    main()
