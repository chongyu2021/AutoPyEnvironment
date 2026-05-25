[**Read in Chinese**](README.zh.md) | [中文版](README.zh.md)

# AutoPyEnvironment

**Auto Python Environment Setup** — a Claude Code skill that automatically configures a complete Python development environment for any GitHub project.

## Features

- **One-shot setup**: Give a GitHub URL, get a working environment
- **Cross-platform**: Windows (PowerShell) & Linux (bash)
- **Smart dependency handling**: Detects `requirements.txt`, `pyproject.toml`, `setup.py`, `environment.yml`, Pipfile, Poetry
- **Network resilience**: Automatic retry, proxy support, PyPI mirror fallback
- **PyTorch & CUDA**: Auto-detects CUDA version and installs matching PyTorch build (cu124, cu121, cu118, CPU)
- **HuggingFace integration**: Downloads model weights with mirror fallback (`hf-mirror.com`), resume support, gated model token support
- **Environment flexibility**: Supports both conda and venv, asks preferences once upfront
- **Smoke test**: Verifies installation with import checks, CUDA test, and project tests

## How It Works

```
User: /auto-pyenv https://github.com/user/repo
                           │
                           ▼
┌─────────────────────────────────────────────┐
│  1. Parse URL & validate repo exists        │
│  2. Detect system (OS, Python, CUDA, etc.)  │
│  3. Collect preferences (one prompt)        │
│  4. Clone repository                        │
│  5. Analyze project structure               │
│  6. Create environment (conda/venv)         │
│  7. Install deps with network fallback       │
│  8. Download HuggingFace weights            │
│  9. Run smoke test & report                 │
└─────────────────────────────────────────────┘
                           │
                           ▼
              Ready-to-use environment!
```

## Requirements

- **Claude Code** (for the skill)
- **Python** 3.9+
- **Git** installed and available in PATH
- **Conda** (optional, for conda-based environments)
- **NVIDIA GPU + drivers** (optional, for CUDA support)

## Installation

### Option 1: Clone this repo (recommended)

```bash
git clone https://github.com/your-username/AutoPyEnvironment.git
cd AutoPyEnvironment
```

The skill is available at `.claude/skills/auto-pyenv/SKILL.md` and is automatically loaded when you run Claude Code from this directory.

### Option 2: Global install

```bash
# Copy the skill to your global Claude Code skills directory
mkdir -p ~/.claude/skills/auto-pyenv
cp .claude/skills/auto-pyenv/SKILL.md ~/.claude/skills/auto-pyenv/
# Also copy the scripts directory (referenced by the skill)
cp -r scripts ~/.claude/skills/auto-pyenv/scripts
```

Then update the `$SKILL_DIR` references in `SKILL.md` to point to `~/.claude/skills/auto-pyenv`.

## Usage

Start Claude Code in the project directory and run:

```
/auto-pyenv https://github.com/huggingface/transformers
```

Or use the helper script directly:

```bash
# Detect system info
python3 scripts/auto_pyenv.py detect-system

# Analyze a project
python3 scripts/auto_pyenv.py parse-project /path/to/project

# Get PyTorch install recommendation
python3 scripts/auto_pyenv.py recommend-torch --cuda-version 12.1

# Download a HuggingFace model
python3 scripts/auto_pyenv.py download-hf --model bert-base-uncased --save-dir ./models

# Run smoke test
python3 scripts/auto_pyenv.py smoke-test /path/to/project
```

## Script Reference

| Command | Description |
|---------|-------------|
| `detect-system` | Detect OS, Python version, CUDA version, GPU, conda availability |
| `parse-project <path>` | Analyze project dependencies, framework, Python version requirements |
| `recommend-torch [--cuda-version]` | Recommend PyTorch version and install command based on CUDA version |
| `download-hf --model NAME [--mirror] [--token]` | Download HuggingFace model with mirror fallback |
| `test-imports --packages PKG1 PKG2 ...` | Test if packages can be imported |
| `smoke-test <dir> [--weights-dir]` | Comprehensive environment verification |

## Configuration (config.json)

The skill reads from `config.json` at startup and skips all interactive prompts when configured. Edit this file to set your preferences:

```json
{
  "repo_dir": "",         // Parent dir for cloned repos (empty = ~/projects/)
  "proxy": "",            // HTTP/HTTPS proxy (e.g. "http://127.0.0.1:7890")
  "hf_mirror": "",        // HuggingFace mirror (e.g. "https://hf-mirror.com")
  "pypi_mirror": "",      // PyPI mirror (e.g. "https://pypi.tuna.tsinghua.edu.cn/simple")
  "package_manager": "",  // "conda" or "venv" (empty = auto-detect)
  "python_version": "",   // Python version (empty = auto-detect from project)
  "weights_dir": "./models",
  "data_dir": "./data",
  "hf_token": "",         // Token for gated HuggingFace models
  "clone_depth": 1        // Shallow clone depth
}
```

Leave a field empty (`""`) to let the skill auto-detect or skip. The skill checks for config in this order:

1. `config.json` in the skill directory (project-level config)
2. `$repoDir/.claude/auto-pyenv.json` (repo-specific override)

If no config file is found, the skill will ask you once and then save your answers to `config.json` for future runs.

### Auto-detected values

These are detected at runtime (not stored in config):

| Info | How it's detected |
|------|-------------------|
| Python version | From project README or `python_requires` in setup.py |
| CUDA version | `nvidia-smi` + `nvcc --version` |
| GPU model | `nvidia-smi --query-gpu=name` |
| Package manager | Prefers conda if available, falls back to venv |
| Git availability | `git --version` |

## Architecture

```
AutoPyEnvironment/
├── CLAUDE.md                       # Project documentation
├── README.md                       # This file
├── README.zh.md                    # Chinese version
├── .claude/
│   └── skills/
│       └── auto-pyenv/
│           └── SKILL.md            # Claude Code skill definition
└── scripts/
    └── auto_pyenv.py               # Python helper utilities
```

## Network Troubleshooting

The skill implements a layered network strategy:

1. Try direct connection (120s timeout, 3 retries)
2. Apply user-specified proxy if direct fails
3. Use PyPI mirror for pip installs if provided
4. Use HF mirror (`hf-mirror.com`) for model downloads if primary fails
5. Install packages individually, skipping problematic ones as last resort

For users in China, recommended mirrors:
- PyPI: `https://pypi.tuna.tsinghua.edu.cn/simple`
- HuggingFace: `https://hf-mirror.com`
- GitHub (clone): `https://ghproxy.net/https://github.com/...`

## License

MIT
