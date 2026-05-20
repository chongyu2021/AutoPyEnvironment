# AutoPyEnvironment

**自动 Python 环境配置** — 一个 Claude Code 技能，输入 GitHub 项目链接即可自动完成 Python 开发环境配置。

## 功能

- **一键配置**：给一个 GitHub 链接，得到一个可用的环境
- **跨平台**：支持 Windows（PowerShell）和 Linux（bash）
- **智能依赖分析**：自动识别 `requirements.txt`、`pyproject.toml`、`setup.py`、`environment.yml`、Pipfile、Poetry
- **网络容错**：自动重试、代理支持、PyPI 镜像回退
- **PyTorch & CUDA**：自动检测 CUDA 版本并安装匹配的 PyTorch（cu124、cu121、cu118、CPU）
- **HuggingFace 集成**：下载模型权重，支持镜像回退（hf-mirror.com）、断点续传、Gated 模型 Token 认证
- **环境灵活**：同时支持 conda 和 venv，一次性询问用户偏好
- **冒烟测试**：Import 检查 + CUDA 测试 + 项目测试，确保环境可用

## 工作流程

```
用户: /auto-pyenv https://github.com/user/repo
                           │
                           ▼
┌─────────────────────────────────────────────┐
│  1. 解析 URL 并验证仓库是否存在              │
│  2. 检测系统（OS、Python、CUDA 等）          │
│  3. 收集用户偏好（一次性询问）               │
│  4. 克隆仓库                                │
│  5. 分析项目结构                            │
│  6. 创建环境（conda/venv）                  │
│  7. 安装依赖（网络容错）                     │
│  8. 下载 HuggingFace 权重                   │
│  9. 运行冒烟测试并输出报告                   │
└─────────────────────────────────────────────┘
                           │
                           ▼
              环境准备就绪，可以直接使用！
```

## 环境要求

- **Claude Code**（使用技能需要）
- **Python** 3.9+
- **Git** 已安装并加入 PATH
- **Conda**（可选，使用 conda 环境时需要）
- **NVIDIA GPU + 驱动**（可选，使用 CUDA 时需要）

## 安装方法

### 方式一：克隆本仓库（推荐）

```bash
git clone https://github.com/your-username/AutoPyEnvironment.git
cd AutoPyEnvironment
```

技能文件位于 `.claude/skills/auto-pyenv/SKILL.md`，当在此目录下运行 Claude Code 时会自动加载。

### 方式二：全局安装

```bash
# 将技能复制到 Claude Code 全局技能目录
mkdir -p ~/.claude/skills/auto-pyenv
cp .claude/skills/auto-pyenv/SKILL.md ~/.claude/skills/auto-pyenv/
# 同时复制脚本目录
cp -r scripts ~/.claude/skills/auto-pyenv/scripts
```

然后更新 `SKILL.md` 中的 `$SKILL_DIR` 路径指向 `~/.claude/skills/auto-pyenv`。

## 使用方法

在项目目录中启动 Claude Code 并运行：

```
/auto-pyenv https://github.com/huggingface/transformers
```

也可以直接使用辅助脚本：

```bash
# 检测系统信息
python3 scripts/auto_pyenv.py detect-system

# 分析项目
python3 scripts/auto_pyenv.py parse-project /path/to/project

# 获取 PyTorch 安装建议
python3 scripts/auto_pyenv.py recommend-torch --cuda-version 12.1

# 下载 HuggingFace 模型
python3 scripts/auto_pyenv.py download-hf --model bert-base-uncased --save-dir ./models

# 运行冒烟测试
python3 scripts/auto_pyenv.py smoke-test /path/to/project
```

## 脚本命令参考

| 命令 | 说明 |
|------|------|
| `detect-system` | 检测 OS、Python 版本、CUDA 版本、GPU、conda 是否可用 |
| `parse-project <path>` | 分析项目依赖、框架类型、Python 版本要求 |
| `recommend-torch [--cuda-version]` | 根据 CUDA 版本推荐 PyTorch 版本和安装命令 |
| `download-hf --model NAME [--mirror] [--token]` | 下载 HuggingFace 模型，支持镜像回退 |
| `test-imports --packages PKG1 PKG2 ...` | 测试包是否能正常导入 |
| `smoke-test <dir> [--weights-dir]` | 全面的环境验证 |

## 技能配置项

调用技能时会一次性询问以下配置：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| 包管理器 | conda（可用时）/ venv | 使用 conda 还是 venv |
| Python 版本 | 3.11 | 环境的 Python 版本 |
| 权重目录 | `$project/models/` | HuggingFace 模型存储位置 |
| 代理 | 无 | HTTP/HTTPS 代理地址 |
| PyPI 镜像 | 官方源 | pip 镜像源（如清华 tuna） |
| HF 镜像 | 官方源 | HuggingFace 镜像（如 hf-mirror.com） |
| HF Token | 无 | 访问 Gated 模型所需的 Token |
| 克隆深度 | 浅克隆（--depth 1） | 完整克隆或浅克隆 |

## 项目结构

```
AutoPyEnvironment/
├── CLAUDE.md                       # 项目文档
├── README.md                       # 英文说明
├── README.zh.md                    # 中文说明
├── .claude/
│   └── skills/
│       └── auto-pyenv/
│           └── SKILL.md            # Claude Code 技能定义
└── scripts/
    └── auto_pyenv.py               # Python 辅助工具
```

## 网络问题处理

技能采用分层网络策略：

1. 直连尝试（120s 超时，3 次重试）
2. 直连失败后使用用户指定的代理
3. 可配置 PyPI 镜像源用于 pip 安装
4. 模型下载主站失败后自动切换到 HF 镜像（hf-mirror.com）
5. 最后手段：逐个安装依赖包，跳过有问题的包

中国大陆用户推荐使用的镜像：
- PyPI：`https://pypi.tuna.tsinghua.edu.cn/simple`
- HuggingFace：`https://hf-mirror.com`
- GitHub（克隆）：`https://ghproxy.net/https://github.com/...`

## License

MIT
