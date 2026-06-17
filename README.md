# Poor Man's DevOps Agent

> 花小钱办大事。没预算买 DataDog？扔上去一个脚本照样能 Debug！

**乞丐版运维助手** - 单文件 AI Debug Agent，支持 Python 2.7+ / 3.x，`scp` 上传即用。

## 快速开始

```bash
git clone https://github.com/vector4wang/poor-mans-devops-agent.git
cd poor-mans-devops-agent
python agent.py
```

或直接：

```bash
curl -fsSL https://raw.githubusercontent.com/vector4wang/poor-mans-devops-agent/main/agent.py | python -
```

## 配置

**方式一：环境变量**
```bash
export DEBUGBOT_API_URL="https://api.deepseek.com/chat/completions"
export DEBUGBOT_API_KEY="sk-xxxxx"
export DEBUGBOT_MODEL="deepseek-chat"
python agent.py
```

**方式二：运行时输入**

```bash
$ python agent.py

API Endpoint: https://api.deepseek.com/chat/completions
API Key    : sk-xxxxx
Model      : deepseek-chat
```

## 支持的模型

OpenAI 兼容 API 均可使用：

| 类型 | 示例 |
|------|------|
| **云服务** | DeepSeek, OpenAI, 阿里通义, 智谱GLM, Kimi, 豆包, 讯飞星火 |
| **本地部署** | Ollama, vLLM, LocalAI, xinference |

## 安全机制

| 机制 | 说明 |
|------|------|
| 命令白名单 | 只允许只读/诊断命令 |
| 危险拦截 | `rm -rf /`, `dd`, `shutdown` 等直接阻断 |
| 人工确认 | 敏感操作执行前需确认 |
| 路径限制 | 只允许访问 `/home`, `/var/log`, `/etc` 等目录 |

## 使用示例

```
[你] 服务响应很慢，帮我看看

[执行] docker stats --no-stream
[执行] docker logs my-service --tail=50

[助手] CPU 占用 89%，可能是 GC 停顿或死循环。建议：
  docker exec my-service jstack
```

## 支持的命令

- **系统**: `ps`, `top`, `free`, `df`, `du`, `uptime`
- **网络**: `curl`, `ping`, `netstat`, `ss`, `dig`, `tcpdump`
- **日志**: `cat`, `grep`, `tail`, `journalctl`, `dmesg`
- **Docker**: `ps`, `logs`, `inspect`, `stats`, `exec`
- **K8s**: `get`, `describe`, `logs`, `top`
- **数据库**: MySQL, PostgreSQL, Redis 只读查询

## License

MIT
