# AutoPyEnvironment

Auto-configure Python project environments via a Claude Code skill.

## Project Structure

```
config.json                          # User preferences (edit this, skip all prompts)
.claude/skills/auto-pyenv/SKILL.md  # Skill definition
scripts/auto_pyenv.py               # Python helper script
```

## Skill Usage

```
/auto-pyenv https://github.com/user/repo
```

The skill will:
1. Parse GitHub URL and clone the repo
2. Analyze project dependencies (README + build files)
3. Read `config.json` for user preferences (no prompts if configured)
4. Create Python environment (conda or venv)
5. Install dependencies with network resilience (proxy/mirror fallback)
6. Download HuggingFace weights (mirror-first strategy)
7. Download datasets if needed
8. Run smoke test and output a report

## Script Reference

```bash
python scripts/auto_pyenv.py detect-system                # Detect OS, Python, CUDA, GPU
python scripts/auto_pyenv.py parse-project <dir>          # Analyze project dependencies
python scripts/auto_pyenv.py recommend-torch               # Recommend PyTorch version
python scripts/auto_pyenv.py download-hf --model NAME      # Download HF model
python scripts/auto_pyenv.py smoke-test <dir>              # Run environment smoke test
python scripts/auto_pyenv.py read-config [path]            # Read configuration
python scripts/auto_pyenv.py write-config [path] --key k=v # Write configuration key
```

## Development

- Skill file uses YAML frontmatter + Markdown format
- Network operations: 120s timeout, up to 3 retries
- Proxy and mirrors are preferred for network resilience
