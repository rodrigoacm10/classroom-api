"""Gera os executáveis locus-api e locus-worker com Nuitka.

Uso, a partir de classroom-api:

    uv run python scripts/build_executables.py
    uv run python scripts/build_executables.py api
    uv run python scripts/build_executables.py worker

Os binários saem em dist/. PostgreSQL, Redis e o .env continuam de fora.
Rode cada executável com o diretório de trabalho na pasta que contém o .env.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
TEMPLATES = ROOT / "src" / "infra" / "email" / "templates"

COMMON_FLAGS = [
    "--mode=onefile",
    f"--output-dir={DIST}",
    "--remove-output",
    "--assume-yes-for-downloads",
    "--lto=no",
    "--low-memory",
    "--jobs=1",
    "--noinclude-pytest-mode=nofollow",
    "--noinclude-unittest-mode=nofollow",
    "--noinclude-setuptools-mode=nofollow",
    "--noinclude-IPython-mode=nofollow",
    "--nofollow-import-to=numpy.f2py",
    "--nofollow-import-to=numpy.testing",
    "--nofollow-import-to=numpy.tests",
    "--nofollow-import-to=pygments",
    f"--include-data-dir={TEMPLATES}=infra/email/templates",
    "--include-package-data=certifi",
    "--include-package-data=botocore",
    "--include-package=psycopg",
    "--include-module=sqlalchemy.dialects.postgresql.psycopg",
    "--include-module=pwdlib.hashers.argon2",
    "--include-module=celery.fixups",
    "--include-module=celery.fixups.django",
    "--include-module=celery.loaders.app",
]

TARGETS: dict[str, dict[str, object]] = {
    "api": {
        "entry": ROOT / "src" / "run_api.py",
        "output": "locus-api",
        "extra": [
            "--include-package=uvicorn",
            "--include-package=limits",
            "--include-package-data=limits",
        ],
    },
    "worker": {
        "entry": ROOT / "src" / "run_worker.py",
        "output": "locus-worker",
        "extra": [
            "--include-module=celery.apps.worker",
            "--include-module=celery.apps.beat",
            "--include-module=celery.app.log",
            "--include-module=celery.app.amqp",
            "--include-module=celery.app.control",
            "--include-module=celery.app.events",
            "--include-module=celery.events.state",
            "--include-module=celery.events.receiver",
            "--include-module=celery.events.dispatcher",
            "--include-module=celery.result",
            "--include-module=celery.worker.components",
            "--include-module=celery.worker.autoscale",
            "--include-module=celery.worker.consumer",
            "--include-module=celery.worker.consumer.delayed_delivery",
            "--include-module=celery.worker.request",
            "--include-module=celery.worker.strategy",
        ],
    },
}


def ensure_patchelf() -> None:
    """O modo onefile no Linux precisa do patchelf para ajustar o RPATH das bibliotecas."""
    if shutil.which("patchelf"):
        return

    tools = ROOT / ".tools"
    binary = tools / "patchelf"
    if not binary.is_file():
        tools.mkdir(parents=True, exist_ok=True)
        print("patchelf não está instalado. Baixando o pacote localmente...", flush=True)
        try:
            subprocess.run(["apt-get", "download", "patchelf"], cwd=tools, check=True)
            deb = next(tools.glob("patchelf_*.deb"))
            extract_root = tools / "root"
            subprocess.run(["dpkg-deb", "-x", str(deb), str(extract_root)], check=True)
            extracted = extract_root / "usr" / "bin" / "patchelf"
            extracted.replace(binary)
            binary.chmod(0o755)
        except (OSError, StopIteration, subprocess.CalledProcessError) as exc:
            raise SystemExit(
                "Não foi possível obter o patchelf. Instale com: sudo apt install patchelf"
            ) from exc

    os.environ["PATH"] = str(tools) + os.pathsep + os.environ.get("PATH", "")


def _worker_data_flags() -> list[str]:
    import celery.utils.static as celery_static

    logo = Path(celery_static.__file__).resolve().parent / "celery_128.png"
    return [f"--include-data-files={logo}=celery/utils/static/celery_128.png"]


def build(name: str) -> None:
    target = TARGETS[name]
    entry = target["entry"]
    extra = target["extra"]
    output = target["output"]
    if not isinstance(entry, Path) or not isinstance(output, str) or not isinstance(extra, list):
        raise RuntimeError(f"Alvo inválido: {name}")

    command = [
        sys.executable,
        "-m",
        "nuitka",
        *COMMON_FLAGS,
        f"--output-filename={output}",
        *extra,
        *(_worker_data_flags() if name == "worker" else []),
        str(entry),
    ]
    env = os.environ.copy()
    src = str(ROOT / "src")
    env["PYTHONPATH"] = src if not env.get("PYTHONPATH") else src + os.pathsep + env["PYTHONPATH"]
    env["PYTHONUNBUFFERED"] = "1"

    print(f"Compilando {output}...", flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    print(f"Pronto: {DIST / output}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compila a API e o worker com Nuitka.")
    parser.add_argument(
        "target",
        nargs="?",
        choices=["all", "api", "worker"],
        default="all",
        help="O que compilar. O padrão compila os dois.",
    )
    args = parser.parse_args()
    ensure_patchelf()
    names = ["api", "worker"] if args.target == "all" else [args.target]
    for name in names:
        build(name)


if __name__ == "__main__":
    main()
