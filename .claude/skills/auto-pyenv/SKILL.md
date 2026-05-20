---
name: auto-pyenv
description: |
  Automatically configure a complete Python environment for any GitHub project.
  Supports Windows & Linux. Clones repo, sets up conda/venv, installs
  dependencies (PyTorch, CUDA, etc.) with network-mirror fallback, downloads
  HuggingFace weights, and runs a smoke test.
argument-hint: [github-url]
allowed-tools: Read, Write, Edit, Bash, PowerShell, Glob, Grep, WebFetch, WebSearch
---

# Auto Python Environment Setup Skill

## Overview
One-shot environment bootstrapper for any Python project on GitHub.

**Platforms**: Windows (PowerShell) · Linux (bash)
**User provides**: a GitHub URL + preferences (one-time prompt)
**Skill delivers**: working environment + installed deps + test report

---

## Step 1 — Detect OS & Parse Input

### Detect OS
Use the platform info from the environment to determine the OS:
```powershell
# Windows:
$isWindows = $true
$homeDir = $env:USERPROFILE
$sep = "\"
$python = "python"
```
```bash
# Linux:
is_windows=false
home_dir="$HOME"
sep="/"
python="python3"
```

Set these variables once and use them throughout.

### Parse GitHub URL
Extract `$repoFullName` (owner/repo) from `$ARGUMENTS`:
- `https://github.com/owner/repo` → `owner/repo`
- `owner/repo` → as-is
- `git@github.com:owner/repo.git` → `owner/repo`

Validate:
```powershell
# Windows
git ls-remote "https://github.com/$repoFullName" HEAD
```
```bash
# Linux
git ls-remote "https://github.com/$repoFullName" HEAD
```

Set derived variables:
```
repoName = second segment of repoFullName
repoDir  = homeDir/sep/projects/sep/repoName
```

---

## Step 2 — Load Configuration

Before asking anything, check for an existing config file. Look in order:

1. `$SKILL_DIR/config.json` (project-level config)
2. `$repoDir/.claude/auto-pyenv.json` (repo-specific override)

If found, read all values from it and **skip all prompts** — proceed silently.

If not found, ask the user once, then save their answers to `$SKILL_DIR/config.json`:

```python
# Use the helper script to read/write config
python3 "$SKILL_DIR/scripts/auto_pyenv.py" read-config "$SKILL_DIR/config.json"
```

Config values (edit `config.json` to change defaults):

| Key | Purpose | Default |
|-----|---------|---------|
| `proxy` | Proxy/VPN address | `""` (none) |
| `hf_mirror` | HuggingFace mirror URL | `""` (official) |
| `pypi_mirror` | PyPI mirror URL | `""` (official) |
| `package_manager` | conda or venv | `""` (auto-detect) |
| `python_version` | Python version (auto-detected from project if empty) | `""` (auto) |
| `weights_dir` | Where to save models | `"./models"` |
| `data_dir` | Where to save datasets | `"./data"` |
| `hf_token` | HuggingFace token | `""` (none) |
| `clone_depth` | Shallow clone depth | `1` (shallow) |

> **Note**: `package_manager` empty means auto-detect (conda > venv if available). Set to `"conda"` or `"venv"` to force a choice.

Auto-detected values (always detected, never stored in config):

| Info | Windows | Linux |
|------|---------|-------|
| Python | `python --version` | `python3 --version` |
| Conda | `conda --version` | `conda --version` |
| GPU/CUDA | `nvidia-smi --query-gpu=driver_version,name --format=csv,noheader` | same |
| Git | `git --version` | same |
| pip | `pip --version` | `pip3 --version` |

**Priority rules** (apply throughout the entire flow):
- **Proxy first**: if user provides a proxy, all network ops go through it (git clone, pip install, HF downloads). Fall through to other methods only on failure.
- **HF mirror first**: if user provides an HF mirror, download weights from it directly, not from official.
- **PyPI mirror on demand**: if user provides a PyPI mirror, pass `-i` to pip install when needed.

---

## Step 3 — Clone Repository

```bash
# Set proxy before clone if user provided one
if [ -n "$PROXY" ]; then
  export HTTP_PROXY="$PROXY"
  export HTTPS_PROXY="$PROXY"
fi

git clone --depth 1 "https://github.com/$repoFullName" "$repoDir"
cd "$repoDir"
```

If clone fails:
1. Try ghproxy mirror: `git clone --depth 1 "https://ghproxy.net/https://github.com/$repoFullName" "$repoDir"`
2. If still failing, report and ask

---

## Step 4 — Analyze the Project

Scan for build files AND the README (critical for paper repos):

### 4a — Build files (priority order)
1. `environment.yml`
2. `requirements.txt`
3. `pyproject.toml`
4. `setup.py` / `setup.cfg`
5. `Pipfile`
6. `poetry.lock`

### 4b — README (primary source for paper reproduction repos)

Paper reproduction repos often put the most critical environment information ONLY in the README, not in build files. README info takes **priority** over build files.

```bash
# Find README files
ls "$repoDir"/README* "$repoDir"/readme* 2>/dev/null
```

Scan the README for:
- **Python version**: `Python 3.8+`, `requires Python >= 3.9`
- **PyTorch version**: `torch==1.13.1+cu117`, `PyTorch 2.0`, `conda install pytorch==1.12.1`
- **CUDA version**: `CUDA 11.7`, `cuda=11.3`, `cu117`
- **Install commands**: `pip install -r requirements.txt`, `conda env create -f environment.yml`, `bash install.sh`
- **Special deps**: `flash-attn`, `xformers`, `ninja`, `cuda-extensions` (packages needing compilation)
- **Model weights**: references to HF model names, download URLs
- **Dataset**: where and how to prepare data

> **Rule of thumb**: Paper repos often pin exact torch/CUDA combinations (e.g. "Our code is tested on PyTorch 1.13.1 + CUDA 11.7"). These must be adopted faithfully, or functionality may break.

### 4c — Merge analysis results

Run the helper parser to get a structured summary:
```bash
python3 "$SKILL_DIR/scripts/auto_pyenv.py" parse-project "$repoDir"
```

Identify:
- Python version constraint
- Key packages (torch, transformers, diffusers, tensorflow)
- Framework type
- Test directories

---

## Step 5 — Environment Setup

**IMPORTANT**: Each tool call runs in a new shell. Activation does NOT persist.
→ Always use full paths to the environment's python/pip.

### Option A: conda

```bash
conda create -n "$repoName" python=$pythonVersion -y
# Then use:
#   conda run -n "$repoName" python ...
#   conda run -n "$repoName" pip install ...
```

If `environment.yml` exists:
```bash
conda env create -f environment.yml
```

### Option B: venv

```bash
# Linux
python3 -m venv "$repoDir/.venv"
# Use full path:
#   "$repoDir/.venv/bin/python" ...
#   "$repoDir/.venv/bin/pip" ...
```

**Python version resolution** (use this priority):
1. Project requirement (from README → `python_requires` in setup.py/pyproject.toml)
2. Config file `python_version` (if user set one)
3. System default Python

If the resolved version is too new for the project's dependencies (e.g. Python 3.14 has no PyTorch wheels), either:
- conda: `conda create -n "$repoName" python=3.12 -y`
- venv: needs user to install Python 3.12 separately, or fall back to conda

---

## Step 6 — Install Dependencies (Network Resilient)

**Setup**: if user has a proxy, set env vars so pip inherits them automatically:
```bash
if [ -n "$PROXY" ]; then
  export HTTP_PROXY="$PROXY"
  export HTTPS_PROXY="$PROXY"
fi
```

Strategy (proxy first, mirror fallback):
```
   ┌─ Proxy set? ── Proxy first (all traffic through proxy)
   │                 ├─ OK → done
   │                 └─ Fail → fall through to no-proxy flow
   │
   └─ No proxy ──── Direct attempt (120s timeout, up to 3 retries)
                     ├─ OK → done
                     └─ Direct fails
                          ├─ PyPI mirror set? → retry with -i mirror
                          └─ Still failing → install one-by-one, skip failures
```

### 6a — PyTorch

```bash
# Get PyTorch install command from the helper
python3 "$SKILL_DIR/scripts/auto_pyenv.py" recommend-torch --cuda-version "$cudaVersion"
```

Parse JSON output, use the `install_command` field, adapt for your environment:
```bash
# venv on Linux (proxy env already set above):
"$repoDir/.venv/bin/pip" install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# conda:
conda run -n "$repoName" pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

If PyTorch index is unreachable (SSL/timeout):
1. **Proxy set & failing** → proxy is broken, report and abort
2. **No proxy** → ask user if they have a proxy to provide
3. CUDA version fails → try cu121 fallback → try CPU-only

### 6b — Other dependencies

```bash
# requirements.txt (inherits proxy env vars)
"$ENV_PYTHON" -m pip install --timeout 120 -r "$repoDir/requirements.txt"

# pyproject.toml (editable install)
"$ENV_PYTHON" -m pip install --timeout 120 -e "$repoDir"

# With PyPI mirror (if user set one)
if [ -n "$PYPI_MIRROR" ]; then
  "$ENV_PYTHON" -m pip install --timeout 120 -i "$PYPI_MIRROR" -r "$repoDir/requirements.txt"
fi

# Both proxy & mirror exhausted → try one-by-one, skip failures
while IFS= read -r pkg; do
  "$ENV_PYTHON" -m pip install --timeout 120 "$pkg" || echo "FAILED: $pkg"
done < "$repoDir/requirements.txt"
```

Where `$ENV_PYTHON` is either:
- `conda run -n "$repoName" python` (conda)
- `"$repoDir/.venv/bin/python"` (venv, Linux)
- `"$repoDir\.venv\Scripts\python.exe"` (venv, Windows)

---

## Step 7 — Download Weights & Datasets

### 7a — HuggingFace Models
Use the weights directory from the user's answer (default: `$repoDir/models/`).

**Priority**: if user set an HF mirror → try mirror first, fall back to official

1. Search for model references in the code:
```bash
grep -r "from_pretrained\|pretrained_model_name_or_path\|model_id" "$repoDir" --include="*.py" 2>/dev/null | head -20
```

2. For each unique model ID found, download:
```bash
# Set proxy before download if user provided one
if [ -n "$PROXY" ]; then
  export HTTP_PROXY="$PROXY"
  export HTTPS_PROXY="$PROXY"
fi

"$ENV_PYTHON" "$SKILL_DIR/scripts/auto_pyenv.py" download-hf \
  --model "$modelName" \
  --save-dir "$weightsDir" \
  --mirror "$hfMirror" \
  --token "$hfToken"
```

3. The helper script handles:
   - **Mirror first** (if set): try mirror URL → fallback to official if mirror fails
   - **Proxy + Mirror**: if both set, traffic goes through proxy to the mirror
   - Resume on partial downloads, skip already-downloaded, auth errors

4. If the project has config files referencing remote model paths, update them to local paths (briefly confirm with user).

### 7b — Datasets
If the user specified a dataset directory, check the README and code for dataset references:

```bash
grep -r "dataset\|data_dir\|data_path\|load_dataset" "$repoDir" --include="*.py" 2>/dev/null | head -15
```

If the project uses HuggingFace `datasets`:
```bash
"$ENV_PYTHON" -c "from datasets import load_dataset; ds = load_dataset('$dataset_name', cache_dir='$dataDir'); print(f'Dataset {ds} loaded')"
```

If the README provides download URLs:
- Download to `$dataDir/`
- Verify checksums if provided
- Report any manual download steps the user needs to do

---

## Step 8 — Smoke Test

```bash
# Python version
"$ENV_PYTHON" -c "import sys; print(f'Python {sys.version}')"

# PyTorch (if installed)
"$ENV_PYTHON" -c "
import torch
print(f'PyTorch {torch.__version__}, CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'Device: {torch.cuda.get_device_name(0)}')
"

# Transformers (if installed)
"$ENV_PYTHON" -c "import transformers; print(f'transformers {transformers.__version__}')"

# Project tests (if applicable)
"$ENV_PYTHON" -m pytest "$repoDir/tests" -x --timeout=120 -q 2>/dev/null || echo "No tests or test failure"

# Helper script smoke test
python3 "$SKILL_DIR/scripts/auto_pyenv.py" smoke-test "$repoDir" --weights-dir "$weightsDir"
```

---

## Step 9 — Report

Use a wide report format with clear sections, warnings, and actionable suggestions:

```
  Auto-PyEnv Setup Complete
  ============================================================================
  Project       huggingface/diffusers
  Platform      Windows 10.0.19045  |  Python 3.12.10
  Location      ~/projects/diffusers
  Environment   venv  (.venv)
  Proxy         http://127.0.0.1:6478
  ----------------------------------------------------------------------------
  Dependencies
    PyTorch     2.6.0+cu124          CUDA 12.4
    GPU         Available            NVIDIA RTX 5070 Laptop GPU
    transformers  5.8.1
    diffusers     0.39.0.dev0
    Others      42/42 installed
  ----------------------------------------------------------------------------
  Models & Data
    bert-base-uncased                 168 MB  local cache
    runwayml/stable-diffusion-v1-5    2.3 GB  local
    Dataset: coco2017                 25 GB   ~/projects/repo/data/coco
  ----------------------------------------------------------------------------
  Tests
    Python import    torch  transformers  diffusers
    CUDA             device_count=1
    pytest           15/15 passed
    Inference        bert-base-uncased output shape [1,8]
  ----------------------------------------------------------------------------
  Warnings
    ! RTX 5070 (sm_120) too new for PyTorch 2.6 (max sm_90)
      -> Try: pip install --upgrade --pre torch --index-url
             https://download.pytorch.org/whl/nightly/cu124
  ============================================================================
  Activate:  conda activate repo
             source .venv/bin/activate
```

List any failures and warnings clearly. For GPU compatibility issues, suggest the correct fix (nightly build, different CUDA version, etc.).

---

## Important Notes

- **Cross-platform**: Skill supports both Windows (PowerShell) and Linux (bash). OS is auto-detected.
- **Do NOT install CUDA drivers** — only the PyTorch CUDA variant. System drivers are user's responsibility.
- **Never use `sudo`** — report system package requirements instead.
- **Disk space**: warn if project + weights > 10 GB.
- **Gated models**: 403 → ask user for HF token.
- **Timeouts**: 120s per operation, up to 3 retries.
- **Python version**:
  - Bleeding-edge Python (3.14+) likely has no PyTorch wheels. Default to 3.11 or 3.12.
  - If user's system Python is too new, install an older version via conda or pyenv.
- **GPU compatibility**: After installing PyTorch, check `torch.cuda.get_arch_list()` against the GPU's compute capability. New GPUs (RTX 50-series, Blackwell sm_120) may need PyTorch nightly. Detect this during smoke test and warn.
- **Fallback plan**: leave repo cloned, document attempts, suggest next steps.
