---
kind: dependency_management
name: Python Dependency Management via Flat requirements.txt with Local venv
category: dependency_management
scope:
    - '**'
source_files:
    - requirements.txt
    - .gitignore
---

## What system/approach is used

The repository manages Python dependencies exclusively through a single flat `requirements.txt` file at the repository root. There is no use of modern Python packaging tooling such as `pyproject.toml`, `Pipfile`, `poetry.lock`, `conda`, or vendored third-party packages. Dependencies are installed into a local virtual environment (`venv/`) that is git-ignored, and deployment/installation is documented as `pip install -r requirements.txt`.

## Key files and packages

- **`requirements.txt`** — the sole dependency manifest listing 14 runtime packages: `numpy`, `pandas`, `requests`, `httpx`, `lightgbm`, `scikit-learn`, `joblib`, `fastapi`, `uvicorn`, `pydantic<3`, `matplotlib`, `reportlab`, `apscheduler`, `python-dotenv`. Notably, only `pydantic` carries a version constraint (`<3`); all other packages are declared by name without pinned versions.
- **`venv/`** — the generated virtual environment directory; present in the repo tree but excluded from version control via `.gitignore` (line 5).
- **`.gitignore`** — explicitly ignores `venv/`, `.venv/`, `.env`, and all generated artifacts under `results/`, `reports/generated/`, and `results/datasets/pvgis_cache/`.
- **`PROJECT_CONTEXT.md`, `PROJECT_CONTEXT_SHORT.md`, `README.md`, `BUILD_PROMPT.md`** — all reference installation via `pip install -r requirements.txt`; `BUILD_PROMPT.md` additionally recommends pinning versions in `requirements.txt` and considering a Dockerfile based on `python:3.11-slim`.

## Architecture and conventions

- **Single-file manifest**: All Python dependencies are declared in one top-level `requirements.txt`; there are no per-package or per-module requirement files.
- **No lockfile**: No `requirements.lock`, `poetry.lock`, `Pipfile.lock`, or equivalent exists. The only explicit version pin observed is `pydantic<3` in `requirements.txt`, likely to maintain compatibility with FastAPI's current API surface.
- **Local virtual environments**: Developers create an isolated `venv/` per machine. The presence of `__pycache__/` directories alongside source modules indicates standard pip-installed packages coexisting with the project code.
- **No private registry configuration**: There is no `pip.conf`, `~/.netrc`, `PYPI_URL`, or `--index-url` usage visible in the codebase; dependencies are expected to resolve from the default PyPI.
- **Frontend has no package manager**: The dashboard is pure HTML/CSS/JS served statically; there is no `package.json`, `yarn.lock`, `node_modules`, or CDN references for JS libraries, so frontend dependencies are not managed through a package manager.

## Conventions and constraints

- **Installation command**: The documented and consistently referenced installation method across `README.md`, `PROJECT_CONTEXT.md`, `PROJECT_CONTEXT_SHORT.md`, and `BUILD_PROMPT.md` is `pip install -r requirements.txt`.
- **Version pinning convention**: As of this snapshot, only `pydantic` is constrained (`<3`). The `BUILD_PROMPT.md` task explicitly calls out that `requirements.txt` should be updated to pin versions rather than leaving them unpinned, indicating that full pinning is a planned improvement rather than current practice.
- **Virtual environment scope**: `venv/` and `.venv/` are both ignored, signaling that each developer maintains their own isolated environment; the checked-out `venv/` shown in the tree is a local artifact and must not be shared.
- **Generated data isolation**: All runtime-generated state (SQLite databases, model artifacts, caches, reports) lives under `results/` and `reports/generated/` and is fully git-ignored, keeping the dependency graph decoupled from transient outputs.
- **No vendoring**: Third-party Python packages are not vendored into the repository; they are resolved at install time from PyPI.