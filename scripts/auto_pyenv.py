#!/usr/bin/env python3
"""
AutoPyEnv — Helper utilities for the auto-pyenv Claude Code skill.

Usage:
    python auto_pyenv.py detect-system
    python auto_pyenv.py parse-project <path>
    python auto_pyenv.py recommend-torch [--cuda-version CUDA_VERSION]
    python auto_pyenv.py download-hf --model NAME [--save-dir DIR] [--mirror URL] [--token TOKEN] [--proxy URL]
    python auto_pyenv.py read-config [path]
    python auto_pyenv.py write-config [path] --key proxy=http://127.0.0.1:7890
    python auto_pyenv.py test-imports [--packages PKG1 PKG2 ...]
    python auto_pyenv.py smoke-test <project-dir> [--weights-dir DIR]
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# System Detection
# ──────────────────────────────────────────────

def detect_system() -> dict:
    """Detect OS, Python, CUDA, conda, etc."""
    info = {
        "os": sys.platform,
        "os_version": "",
        "python_version": sys.version.split()[0],
        "python_path": sys.executable,
        "has_conda": False,
        "conda_version": "",
        "has_git": False,
        "cuda_version": "",
        "cuda_driver_version": "",
        "gpu_name": "",
        "gpu_count": 0,
    }

    # OS version
    if sys.platform == "win32":
        info["os"] = "windows"
        try:
            ver = sys.getwindowsversion()
            info["os_version"] = f"{ver.major}.{ver.minor}.{ver.build}"
        except Exception:
            info["os_version"] = platform.version()
    elif sys.platform == "linux":
        info["os"] = "linux"
        try:
            with open("/etc/os-release") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        info["os_version"] = line.split("=", 1)[1].strip().strip('"')
                        break
        except Exception:
            pass
    elif sys.platform == "darwin":
        info["os"] = "macos"
        try:
            info["os_version"] = subprocess.check_output(
                ["sw_vers", "-productVersion"], text=True, timeout=5
            ).strip()
        except Exception:
            pass

    # Conda
    conda_exe = shutil.which("conda")
    if conda_exe:
        try:
            out = subprocess.check_output(
                [conda_exe, "--version"], text=True, timeout=15, stderr=subprocess.STDOUT
            ).strip()
            info["has_conda"] = True
            info["conda_version"] = out.split()[-1] if " " in out else out
        except Exception:
            pass

    # Git
    if shutil.which("git"):
        info["has_git"] = True

    # CUDA via nvidia-smi
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            out = subprocess.check_output(
                [nvidia_smi, "--query-gpu=driver_version,name,count",
                 "--format=csv,noheader"],
                text=True, timeout=15
            ).strip()
            lines = [l.strip() for l in out.split("\n") if l.strip()]
            if lines:
                parts = [p.strip() for p in lines[0].split(",")]
                info["cuda_driver_version"] = parts[0] if len(parts) > 0 else ""
                info["gpu_name"] = parts[1] if len(parts) > 1 else ""
                info["gpu_count"] = len(lines)

                # Rough CUDA version from driver (CUDA 12.x needs driver >= 525+)
                try:
                    driver_ver = float(info["cuda_driver_version"].split(".")[0])
                    if driver_ver >= 550:
                        info["cuda_version"] = "12.4"
                    elif driver_ver >= 525:
                        info["cuda_version"] = "12.1"
                    elif driver_ver >= 450:
                        info["cuda_version"] = "11.8"
                    else:
                        info["cuda_version"] = "11.7"
                except (ValueError, IndexError):
                    pass
        except Exception:
            pass

    # Also try `nvcc --version` for exact CUDA Toolkit version
    nvcc = shutil.which("nvcc") or shutil.which("nvcc.exe")
    if nvcc:
        try:
            out = subprocess.check_output(
                [nvcc, "--version"], text=True, timeout=15, stderr=subprocess.STDOUT
            )
            m = re.search(r"release (\d+\.\d+)", out)
            if m:
                info["cuda_version"] = m.group(1)
        except Exception:
            pass

    return info


# ──────────────────────────────────────────────
# Project Parsing
# ──────────────────────────────────────────────

def parse_project(project_path: str) -> dict:
    """Analyze a project directory and return dependency info."""
    info = {
        "python_requires": "",
        "has_torch": False,
        "has_tf": False,
        "has_transformers": False,
        "has_diffusers": False,
        "has_sentence_transformers": False,
        "framework": "unknown",
        "build_system": "unknown",
        "requirements_files": [],
        "extra_requirements": [],
        "has_tests": False,
        "main_module": "",
        "dev_requirements": [],
    }

    proj = Path(project_path)
    if not proj.is_dir():
        return {"error": f"Directory not found: {project_path}"}

    # Check for build files
    checks = {
        "requirements.txt": "requirements.txt",
        "environment.yml": "environment.yml",
        "pyproject.toml": "pyproject.toml",
        "setup.py": "setup.py",
        "setup.cfg": "setup.cfg",
        "Pipfile": "Pipfile",
        "poetry.lock": "poetry.lock",
    }

    for key, filename in checks.items():
        p = proj / filename
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="ignore")
            info["requirements_files"].append(filename)

            if filename == "pyproject.toml":
                info["build_system"] = "pyproject"
                _check_deps_toml(content, info)
            elif filename == "requirements.txt":
                info["build_system"] = "pip"
                _check_deps_text(content, info)
            elif filename == "setup.py":
                info["build_system"] = "setuptools"
                _check_deps_text(content, info)
            elif filename == "setup.cfg":
                _check_deps_text(content, info)
            elif filename == "environment.yml":
                info["build_system"] = "conda"
                _check_deps_text(content, info)
            elif filename == "Pipfile":
                info["build_system"] = "pipenv"
                _check_deps_text(content, info)

            # Python version requirement
            m = re.search(r'python_requires\s*[=]=?\s*["\']([^"\']+)["\']', content)
            if m:
                info["python_requires"] = m.group(1)
            m = re.search(r'python\s*=\s*"([^"]+)"', content)  # pyproject.toml [tool.poetry.dependencies]
            if m:
                info["python_requires"] = m.group(1)

    # Check for test directories
    for test_dir in ["tests", "test"]:
        if (proj / test_dir).is_dir():
            info["has_tests"] = True
            break
    if list(proj.glob("test_*.py")) or list(proj.glob("*_test.py")):
        info["has_tests"] = True

    # Determine main module
    for init in ["main.py", "app.py", "cli.py", "run.py"]:
        if (proj / init).is_file():
            info["main_module"] = init.replace(".py", "")
            break
    # Try to find package name from pyproject or setup
    setup_py = proj / "setup.py"
    if setup_py.exists():
        m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', setup_py.read_text(encoding="utf-8", errors="ignore"))
        if m:
            info["package_name"] = m.group(1)

    # Scan README for version pins (paper repos often put deps only here)
    readme_info = _scan_readme(proj)
    info["readme"] = readme_info
    # README versions override build-file findings
    if readme_info.get("python_requires"):
        info["python_requires"] = readme_info["python_requires"]
    if readme_info.get("has_torch"):
        info["has_torch"] = True
    if readme_info.get("has_transformers"):
        info["has_transformers"] = True

    # Determine framework
    if info["has_torch"]:
        info["framework"] = "pytorch"
    elif info["has_tf"]:
        info["framework"] = "tensorflow"

    return info


def _scan_readme(proj: Path) -> dict:
    """Scan README files for Python/PyTorch/CUDA version requirements.

    Paper reproduction repos often put dependency versions ONLY in the README.
    """
    info = {
        "python_requires": "",
        "torch_requires": "",
        "torch_pin": "",
        "cuda_requires": "",
        "install_commands": [],
        "has_torch": False,
        "has_transformers": False,
        "model_refs": [],
    }

    readme_path = None
    for name in ["README.md", "README", "readme.md", "README.txt"]:
        p = proj / name
        if p.exists():
            readme_path = p
            break

    if not readme_path:
        return info

    text = readme_path.read_text(encoding="utf-8", errors="ignore")

    # Python version: "Python 3.8+", "Python >= 3.9", "requires Python 3.10"
    m = re.search(r"(?:python|requires)\s*(?:>=?|==)?\s*(\d+\.\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        info["python_requires"] = m.group(1)

    # Torch pin: "torch==1.13.1", "torch>=2.0", "pytorch==1.12.1"
    m = re.search(r"(?:torch|pytorch)\s*(==|>=|~=)\s*(\d+\.\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        info["torch_pin"] = f"torch{m.group(1)}{m.group(2)}"
        info["torch_requires"] = m.group(2)
        info["has_torch"] = True

    # CUDA version: "CUDA 11.7", "cuda=11.3", "cu117", "cu121"
    m = re.search(r"(?:CUDA|cuda)\s*(?:version\s*)?[:=]?\s*(\d+\.\d+)", text)
    if m:
        info["cuda_requires"] = m.group(1)
    m = re.search(r"cu(\d{2,3})", text)
    if m:
        code = m.group(1)
        if len(code) == 3:
            info["cuda_requires"] = f"{code[0]}.{code[1:]}"
        else:
            info["cuda_requires"] = f"{code[0]}.{code[1]}"

    # Install commands: lines starting with pip install or conda install
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("pip install") or stripped.startswith("conda install"):
            info["install_commands"].append(stripped)
            if "torch" in stripped.lower():
                info["has_torch"] = True
            if "transformers" in stripped.lower():
                info["has_transformers"] = True

    # Model references: from_pretrained("org/name"), model_id = "org/name"
    for m in re.finditer(
        r'(?:from_pretrained|model_id|model_name|pretrained_model)[=( ]*["\']([a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+)["\']',
        text
    ):
        ref = m.group(1)
        if ref not in info["model_refs"]:
            info["model_refs"].append(ref)

    return info


def _check_deps_text(content: str, info: dict):
    """Scan plaintext dependency content for known packages."""
    for line in content.splitlines():
        line = line.strip().lower()
        if line.startswith("#") or not line:
            continue
        # Strip version specifiers
        pkg = re.split(r"[><=~!;]", line)[0].strip()
        pkg = re.sub(r"[#].*", "", pkg).strip()
        if not pkg:
            continue
        if "torch" in pkg:
            info["has_torch"] = True
            if pkg not in info["extra_requirements"]:
                info["extra_requirements"].append(pkg)
        if pkg.startswith("tensorflow"):
            info["has_tf"] = True
        if "transformers" in pkg:
            info["has_transformers"] = True
        if "diffusers" in pkg:
            info["has_diffusers"] = True
        if "sentence-transformers" in pkg:
            info["has_sentence_transformers"] = True


def _check_deps_toml(content: str, info: dict):
    """Scan pyproject.toml content for dependencies."""
    # Handle [project.dependencies]
    in_deps = False
    bracket_depth = 0
    for line in content.splitlines():
        stripped = line.strip()

        if stripped.startswith("[project.dependencies]"):
            in_deps = True
            continue
        if stripped.startswith("[") and in_deps:
            in_deps = False
            continue
        if in_deps and stripped and not stripped.startswith("#"):
            _check_deps_text(stripped, info)

    # Handle [tool.poetry.dependencies]
    in_poetry = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[tool.poetry.dependencies]"):
            in_poetry = True
            continue
        if stripped.startswith("[") and in_poetry:
            in_poetry = False
            continue
        if in_poetry and "=" in stripped and not stripped.startswith("#"):
            pkg = stripped.split("=")[0].strip().strip('"').strip("'").lower()
            if pkg == "python":
                continue
            if "torch" in pkg:
                info["has_torch"] = True
            if pkg.startswith("tensorflow"):
                info["has_tf"] = True
            if "transformers" in pkg:
                info["has_transformers"] = True
            if "diffusers" in pkg:
                info["has_diffusers"] = True
            if "sentence-transformers" in pkg:
                info["has_sentence_transformers"] = True

    # Try toml parsing for [project]
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            tomllib = None

    if tomllib:
        try:
            data = tomllib.loads(content)
            proj_deps = data.get("project", {}).get("dependencies", [])
            for dep in proj_deps:
                _check_deps_text(dep, info)
        except Exception:
            pass


# ──────────────────────────────────────────────
# PyTorch / CUDA Recommendation
# ──────────────────────────────────────────────

def recommend_torch(cuda_version: Optional[str] = None) -> dict:
    """Recommend the PyTorch install command based on CUDA version."""
    result = {
        "torch_version": "",
        "pip_index_url": "",
        "install_command": "",
        "cuda_compatible": True,
        "note": "",
    }

    if cuda_version:
        try:
            major = int(cuda_version.split(".")[0])
            minor = int(cuda_version.split(".")[1]) if "." in cuda_version else 0
        except (ValueError, IndexError):
            major, minor = 0, 0

        # Map CUDA version to the closest PyTorch build
        # Use unpinned versions so pip resolves with project constraints
        if major >= 12:
            if minor >= 4:
                cuda_tag = "cu124"
                note = "CUDA 12.4 (requires driver >= 550)"
            elif minor >= 1:
                cuda_tag = "cu121"
                note = "CUDA 12.1 (requires driver >= 525)"
            else:
                cuda_tag = "cu121"
                note = "CUDA 12.x → using cu121 (recommended)"
        elif major == 11 and minor >= 8:
            cuda_tag = "cu118"
            note = "CUDA 11.8"
        else:
            cuda_tag = "cu118"
            note = f"CUDA {cuda_version} → using cu118 (fallback)"

        result["torch_version"] = "latest"
        result["pip_index_url"] = f"https://download.pytorch.org/whl/{cuda_tag}"
        result["install_command"] = (
            f"pip install torch torchvision torchaudio --index-url {result['pip_index_url']}"
        )
        result["note"] = note
    else:
        result["torch_version"] = "latest"
        result["pip_index_url"] = "https://download.pytorch.org/whl/cpu"
        result["install_command"] = (
            f"pip install torch torchvision torchaudio --index-url {result['pip_index_url']}"
        )
        result["note"] = "No CUDA detected — installing CPU-only PyTorch"

    # On Windows, cu124 can be problematic; suggest cu121 as safer fallback
    if sys.platform == "win32" and "cu124" in result.get("pip_index_url", ""):
        result["fallback_command"] = result["install_command"].replace("cu124", "cu121")
        result["fallback_note"] = "Windows fallback: cu121 if cu124 fails"

    return result


# ──────────────────────────────────────────────
# HuggingFace Download
# ──────────────────────────────────────────────

def download_hf_model(
    model: str,
    save_dir: str = "models",
    mirror: Optional[str] = None,
    token: Optional[str] = None,
    proxy: Optional[str] = None,
) -> dict:
    """Download a HuggingFace model with mirror fallback.

    Priority: mirror first (if set) → official fallback.
    Proxy is set via env var so huggingface_hub picks it up automatically.
    """
    result = {
        "model": model,
        "save_path": "",
        "success": False,
        "error": "",
        "from_mirror": False,
    }

    save_path = Path(save_dir) / model.replace("/", "--")
    result["save_path"] = str(save_path)

    # Check if already downloaded
    if save_path.exists() and any(save_path.iterdir()):
        result["success"] = True
        result["note"] = "Already exists, skipping"
        return result

    # Ensure huggingface_hub is installed
    _ensure_hf_hub()

    save_path.mkdir(parents=True, exist_ok=True)

    # Set proxy if provided (overrides env)
    env_backup = os.environ.copy()
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy

    # Mirror first (if set), official as fallback
    urls_to_try = []
    if mirror:
        urls_to_try.append(("mirror", mirror))
    urls_to_try.append(("official", "https://huggingface.co"))

    for source_name, base_url in urls_to_try:
        try:
            if source_name == "mirror":
                os.environ["HF_ENDPOINT"] = base_url

            cmd = [
                sys.executable, "-m", "huggingface_hub", "download",
                "--resume-download",
                model,
                "--local-dir", str(save_path),
                "--local-dir-use-symlinks", "False",
            ]
            if token:
                cmd.extend(["--token", token])

            subprocess.run(cmd, check=True, timeout=600)
            result["success"] = True
            result["from_mirror"] = source_name == "mirror"
            result["note"] = f"Downloaded via {source_name}"
            return result

        except subprocess.TimeoutExpired:
            result["error"] = f"Timeout downloading from {source_name}"
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            if "403" in error_msg and source_name == "official":
                result["error"] = "403 Forbidden. This model may require authentication (use --token)."
            elif "401" in error_msg:
                result["error"] = "401 Unauthorized. A HuggingFace token is required."
            else:
                result["error"] = f"Download error from {source_name}: {error_msg[:200]}"
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

    # Clean up empty directory on failure
    if save_path.exists() and not any(save_path.iterdir()):
        save_path.rmdir()

    return result


def _ensure_hf_hub():
    """Install huggingface_hub if not available."""
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "huggingface_hub", "-q"],
            timeout=120,
        )


# ──────────────────────────────────────────────
# Testing
# ──────────────────────────────────────────────

def test_imports(packages: list[str]) -> dict:
    """Test that specified packages can be imported."""
    results = {}
    for pkg in packages:
        try:
            out = subprocess.check_output(
                [sys.executable, "-c", f"import {pkg.split('[')[0]}; print({pkg.split('[')[0]}.__version__)"],
                text=True, timeout=30, stderr=subprocess.STDOUT
            )
            results[pkg] = {"status": "ok", "version": out.strip()}
        except subprocess.CalledProcessError as e:
            results[pkg] = {"status": "failed", "error": e.output.strip()}
        except Exception as e:
            results[pkg] = {"status": "failed", "error": str(e)}
    return results


def smoke_test(project_dir: str, weights_dir: Optional[str] = None) -> dict:
    """Run a comprehensive smoke test on the environment."""
    report = {
        "python": {},
        "cuda": {},
        "packages": {},
        "weights": {},
        "project": {},
    }

    # Python info
    report["python"] = {
        "version": sys.version.split()[0],
        "executable": sys.executable,
    }

    # PyTorch check
    try:
        import torch
        report["packages"]["torch"] = {
            "version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda if hasattr(torch, "version") and hasattr(torch.version, "cuda") else "N/A",
        }
        if torch.cuda.is_available():
            report["cuda"] = {
                "device_count": torch.cuda.device_count(),
                "device_name": torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else "N/A",
            }
    except ImportError:
        report["packages"]["torch"] = {"status": "not installed"}

    # transformers check
    try:
        import transformers  # noqa: F401
        report["packages"]["transformers"] = {"version": transformers.__version__}
    except ImportError:
        report["packages"]["transformers"] = {"status": "not installed"}

    # diffusers check
    try:
        import diffusers  # noqa: F401
        report["packages"]["diffusers"] = {"version": diffusers.__version__}
    except ImportError:
        report["packages"]["diffusers"] = {"status": "not installed"}

    # Check weights directory
    if weights_dir and Path(weights_dir).exists():
        wd = Path(weights_dir)
        models_found = [str(p.relative_to(wd)) for p in wd.iterdir() if p.is_dir()]
        report["weights"] = {
            "path": weights_dir,
            "model_count": len(models_found),
            "models": models_found[:10],
            "size_mb": _get_dir_size_mb(wd),
        }

    return report


def _get_dir_size_mb(path: Path) -> float:
    """Calculate directory size in MB."""
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return round(total / (1024 * 1024), 1)


# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

DEFAULT_CONFIG = {
    "proxy": "",
    "hf_mirror": "",
    "pypi_mirror": "",
    "package_manager": "",
    "python_version": "",
    "weights_dir": "./models",
    "data_dir": "./data",
    "hf_token": "",
    "clone_depth": 1,
}


def read_config(path: str) -> dict:
    """Read config from a JSON file. Returns defaults if file doesn't exist."""
    config_path = Path(path)
    if not config_path.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with open(config_path) as f:
            data = json.load(f)
        # Merge with defaults (fill in any missing keys, skip comments)
        merged = dict(DEFAULT_CONFIG)
        merged.update({k: v for k, v in data.items() if not k.startswith("_")})
        return merged
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: failed to read config {path}: {e}", file=sys.stderr)
        return dict(DEFAULT_CONFIG)


def write_config(path: str, config: dict):
    """Write config to a JSON file, preserving existing values."""
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    # Merge with existing if any
    existing = read_config(path)
    existing.update({k: v for k, v in config.items() if v != "" or k not in existing})
    with open(config_path, "w") as f:
        json.dump(existing, f, indent=2)
        f.write("\n")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AutoPyEnv — Python environment utilities")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # detect-system
    subparsers.add_parser("detect-system", help="Detect system information")

    # read-config
    p_readcfg = subparsers.add_parser("read-config", help="Read config from JSON file")
    p_readcfg.add_argument("path", nargs="?", default="config.json", help="Path to config file")

    # write-config
    p_writecfg = subparsers.add_parser("write-config", help="Write config to JSON file")
    p_writecfg.add_argument("path", nargs="?", default="config.json", help="Path to config file")
    p_writecfg.add_argument("--key", "-k", action="append", help="Key=value pairs (e.g. proxy=http://...)")

    # parse-project
    p_parse = subparsers.add_parser("parse-project", help="Analyze a project directory")
    p_parse.add_argument("path", help="Path to the project directory")

    # recommend-torch
    p_torch = subparsers.add_parser("recommend-torch", help="Recommend PyTorch install command")
    p_torch.add_argument("--cuda-version", default=None, help="CUDA version (e.g., 12.1)")

    # download-hf
    p_hf = subparsers.add_parser("download-hf", help="Download HuggingFace model")
    p_hf.add_argument("--model", required=True, help="HuggingFace model name (e.g., runwayml/stable-diffusion-v1-5)")
    p_hf.add_argument("--save-dir", default="models", help="Directory to save the model")
    p_hf.add_argument("--mirror", default=None, help="HF mirror URL (e.g., https://hf-mirror.com)")
    p_hf.add_argument("--token", default=None, help="HuggingFace authentication token")
    p_hf.add_argument("--proxy", default=None, help="Proxy URL (e.g., http://127.0.0.1:7890)")

    # test-imports
    p_test = subparsers.add_parser("test-imports", help="Test package imports")
    p_test.add_argument("--packages", nargs="+", default=[], help="Package names to test")

    # smoke-test
    p_smoke = subparsers.add_parser("smoke-test", help="Run environment smoke test")
    p_smoke.add_argument("project-dir", help="Project directory")
    p_smoke.add_argument("--weights-dir", default=None, help="Weights directory")

    args = parser.parse_args()

    if args.command == "detect-system":
        info = detect_system()
        print(json.dumps(info, indent=2, ensure_ascii=False))

    elif args.command == "read-config":
        cfg = read_config(args.path)
        print(json.dumps(cfg, indent=2, ensure_ascii=False))

    elif args.command == "write-config":
        cfg = read_config(args.path)
        if args.key:
            for kv in args.key:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    cfg[k] = v
        write_config(args.path, cfg)
        print(json.dumps(cfg, indent=2, ensure_ascii=False))

    elif args.command == "parse-project":
        info = parse_project(args.path)
        print(json.dumps(info, indent=2, ensure_ascii=False))

    elif args.command == "recommend-torch":
        result = recommend_torch(args.cuda_version)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "download-hf":
        result = download_hf_model(args.model, args.save_dir, args.mirror, args.token, args.proxy)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["success"] else 1)

    elif args.command == "test-imports":
        results = test_imports(args.packages)
        print(json.dumps(results, indent=2, ensure_ascii=False))

    elif args.command == "smoke-test":
        report = smoke_test(getattr(args, "project-dir"), args.weights_dir)
        print(json.dumps(report, indent=2, ensure_ascii=False))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
