# Poor Man's DevOps Agent

> **花小钱办大事。没预算买 DataDog/PagerDuty？没关系，扔上去一个脚本照样能 Debug！**

```
    _                               _    ____                _
   / \   _ __ ___  __ _  ___ _ __ | |_ / ___|  ___  ___ ___(_) ___  _ __   ___
  / _ \ | '__/ _ \/ _` |/ _ \ '_ \| __|\___ \ / _ \/ __| __| |/ _ \| '_ \ / __|
 / ___ \| | |  __/ (_| |  __/ | | | |_  ___) |  __/ (__| |_| | (_) | | | \__ \
/_/   \_\_|  \___|\__, |\___|_| |_|\__||____/ \___|\___|\__|_|\___/|_| |_|___/
                  |___/
```

**乞丐版运维助手** - 一个跑在生产服务器上的 AI Debug Agent。支持 Python 2.7+ / 3.x，单文件，`scp` 上传就能用。

## TL;DR

```bash
# 一行命令，直接开搞
curl -fsSL https://raw.githubusercontent.com/YOUR_NAME/poor-mans-devops-agent/main/agent.py | python - --help

# 或者 clone 下来
git clone https://github.com/YOUR_NAME/poor-mans-devops-agent.git
cd poor-mans-devops-agent
python agent.py
```

## 🎯 解决什么问题

半夜三点，服务器报警，你登录上去开始手忙脚乱地敲命令：

```bash
ps aux | grep java
tail -f /var/log/xxx.log
docker ps
kubectl get pods
...
```

有没有想过——**如果有个 AI 能帮你做这些？**

Poor Man's DevOps Agent 就是干这个的。你描述问题，AI 来排查：

```
[你] 服务响应很慢，看看是什么问题

[思考中...]

[调用工具: run_command] docker stats --no-stream
[执行] docker stats --no-stream

[工具结果]
CONTAINER ID   NAME         CPU %   MEM USAGE / LIMIT     MEM %   NET I/O           BLOCK I/O
a1b2c3d4e5f6   my-service   89.5%   2GiB / 4GiB          50.2%   1.2MB / 500KB    10MB / 100MB

[助手]
发现问题：容器 CPU 使用率 89.5%，内存使用 50.2%。
建议排查方向：
1. 查看应用日志：`docker logs my-service --tail=100`
2. 检查 GC 情况（如果是 Java）：`docker exec my-service jstat -gc`
3. 查看线程堆栈：`docker exec my-service jstack`
```

## ⚡ 特性

| 特性 | 说明 |
|------|------|
| 🤖 **AI 驱动** | OpenAI 兼容 API，Claude/Ollama/DeepSeek 通吃 |
| 🛡️ **安全第一** | 命令白名单 + 危险命令拦截 + 人工确认 |
| 📦 **零依赖部署** | 单文件，`scp` 上传即用 |
| 🐍 **Python 2/3** | CentOS 6 都能跑 |
| 🔧 **100+ DevOps 命令** | Docker/K8s/MySQL/Redis/Nginx...全覆盖 |

## 🛡️ 安全机制

### 1. 命令白名单
只允许这些操作：
- 📄 文件读取：`cat`, `grep`, `tail`, `head`
- 🔍 进程查看：`ps`, `top`, `pgrep`
- 🌐 网络诊断：`curl`, `ping`, `netstat`, `ss`
- 🐳 Docker 只读：`ps`, `logs`, `inspect`, `stats`
- ☸️ K8s 只读：`get`, `describe`, `logs`
- 🗄️ 数据库查询：`SELECT` 只读

### 2. 危险命令拦截
```python
FORBIDDEN_PATTERNS = [
    r'rm\s+-rf\s+/',       # 删库跑路？不存在的
    r'dd\s+.*of=/dev/',    # 直接写盘？拦住
    r'shutdown',           # 关机？门都没有
    r'chmod\s+777\s+/',    # 777 权限？不行
    ...
]
```

### 3. 人工确认
```bash
============================================================
[Bash] 需要执行以下操作:
============================================================
docker exec -it my-container /bin/bash
============================================================

确认执行? (y/n/q): y
```

### 4. 安全只读命令免确认
`cat /var/log/xxx.log`、`ps aux` 这种只读命令，直接执行，不用确认。

## 🚀 快速开始

### 方式一：环境变量

```bash
export DEBUGBOT_API_URL="https://api.deepseek.com/chat/completions"
export DEBUGBOT_API_KEY="sk-xxxxx"
export DEBUGBOT_MODEL="deepseek-v4-pro"

python agent.py
```

### 方式二：运行时输入

```bash
$ python agent.py

    ╔═══════════════════════════════════════════════════════╗
    ║     Poor Man's DevOps Agent - 乞丐版运维助手         ║
    ╚═══════════════════════════════════════════════════════╝

API URL: https://api.deepseek.com/chat/completions
API Key: sk-xxxxx
Model (直接回车使用 gpt-4o): deepseek-v4-pro

[你]
```

### 方式三：懒人用法

```bash
# 一行命令，不需要 clone
curl -s https://raw.githubusercontent.com/YOUR_NAME/poor-mans-devops-agent/main/agent.py > /tmp/agent.py
python /tmp/agent.py
```

## 🎮 使用示例

### 查看服务状态
```
[你] 看看 Docker 容器状态

[执行] docker ps -a
CONTAINER ID   IMAGE          STATUS          PORTS
a1b2c3d4e5f6   my-service     Up 2 hours      8080->8080/tcp
b2c3d4e5f6a1   redis          Up 5 days       6379->6379/tcp

[助手]
容器状态正常：
- my-service: 运行 2 小时，端口映射 8080->8080
- redis: 运行 5 天，连接数正常

需要查看更详细的信息吗？
```

### 分析日志问题
```
[你] 这个错误是什么意思？
  ERROR: Connection refused to database

[调用工具: run_command]
[执行] docker logs my-service --tail=50 | grep -A5 "Connection refused"

[工具结果]
2024-01-15 03:23:11 ERROR Database connection failed
2024-01-15 03:23:11 ERROR Connection refused to database
2024-01-15 03:23:12 ERROR Retry attempt 1/3
2024-01-15 03:23:15 ERROR Connection refused to database

[助手]
数据库连接被拒绝，可能原因：
1. 数据库服务挂了 → 检查 `docker ps` 确认 redis/mysql 状态
2. 网络不通 → 检查容器网络 `docker network ls`
3. 连接数满 → `redis-cli info clients`

建议先检查数据库是否正常运行。
```

### 排查性能问题
```
[你] 服务器负载很高，什么原因

[执行] top -bn1 | head -20
[执行] docker stats --no-stream
[执行] df -h

[助手]
分析结果：
1. 容器 my-service CPU 占用 89%，是主要负载来源
2. 磁盘空间正常，内存使用 78%
3. 可能是 GC 停顿或死循环

建议：
- `docker logs my-service` 查看应用日志
- `docker exec my-service jstack` 查看线程堆栈（如果是 Java）
```

## 📋 支持的命令

### 系统监控
```
ps, top, htop, vmstat, iostat, sar, free, df, du, uptime
```

### 网络诊断
```
curl, wget, ping, traceroute, mtr, nslookup, dig, netstat, ss, tcpdump, nmap
```

### Docker
```
docker ps, logs, inspect, stats, images, top, port
docker-compose ps, logs
```

### Kubernetes
```
kubectl get, describe, logs, top, events, cluster-info
helm list, get
```

### 数据库
```
mysql, psql, redis-cli, mongosh
```

### 日志
```
journalctl, tail, grep, cat, less
dmesg, last, lastlog
```

### 编程语言
```
python, pip, node, npm, java, mvn, go, cargo, php
```

## 🔧 自定义

### 添加允许的命令

```python
# agent.py 中添加
ALLOWED_COMMANDS = [
    # ... 现有命令 ...
    r'^supervisorctl\s+',  # 添加 Supervisor
    r'^celery\s+',         # 添加 Celery
]

# 或者添加安全只读命令（不需要确认）
SAFE_READONLY_PATTERNS = [
    # ...
    r'^supervisorctl\s+status\s+',  # 只读查看状态
]
```

### 修改允许的路径

```python
ALLOWED_PATHS = [
    # ... 现有路径 ...
    '/opt/myapp',   # 添加你的应用目录
    '/data2',
]
```

### 调整超时

```python
COMMAND_TIMEOUT = 60  # 默认 30 秒
MAX_OUTPUT_LINES = 1000  # 最大输出行数
```

## ⚠️ 注意事项

1. **不要执行危险的修改操作** - agent 会拦截，但总有漏网之鱼
2. **敏感环境慎用** - 日志、配置可能包含敏感信息
3. **建议配合 VPN/跳板机使用** - 安全访问生产环境
4. **建议设置 API 额度限制** - 防止滥用

## 🛠️ 开发

```bash
# 克隆
git clone https://github.com/YOUR_NAME/poor-mans-devops-agent.git

# 调试模式
python agent.py --debug

# 测试
python -m py_compile agent.py
```

## 📝 License

MIT - 看谁先搞定生产问题 🎯

---

**Q: 为什么叫"乞丐版"？**

A: 因为没钱买 DataDog/Sumo Logic/New Relic/PagerDuty...
   但有手有脚有 SSH，还有一颗不想半夜爬起来 Debug 的心。
   花小钱办大事，赛博朋克精神，你懂的。
