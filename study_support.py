"""Portable input verification and numeric report formatting for new studies."""

import hashlib
import json
import shutil
import time
from pathlib import Path

import matplotlib
import requests

matplotlib.use("Agg")
from matplotlib import pyplot as plt


ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "reports"


def snapshot(name):
    spec = json.loads((ROOT / "data/source-manifest.json").read_text(encoding="utf-8-sig"))[name]
    path = ROOT / "data/raw" / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".part")
        with requests.get(spec["url"], params=spec.get("query"), stream=True, timeout=(12, 90)) as response:
            response.raise_for_status()
            response.raw.decode_content = True
            with temporary.open("wb") as handle:
                shutil.copyfileobj(response.raw, handle, length=256 * 1024)
        if file_digest(temporary) != spec["sha256"]:
            raise ValueError(f"{name} differs from the pinned input manifest.")
        temporary.replace(path)
    if file_digest(path) != spec["sha256"]:
        raise ValueError(f"{name} failed input verification.")
    return path


def file_digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def timed_load(loader):
    started = time.perf_counter()
    value = loader()
    print(f"Validated and loaded data in {time.perf_counter() - started:.3f} s.", flush=True)
    return value


def save(fig, name, source):
    directory = REPORT / "figures"
    directory.mkdir(parents=True, exist_ok=True)
    fig.text(.025, .018, source, fontsize=8, color="#486366", wrap=True)
    fig.tight_layout(rect=(0, .055, 1, .98))
    fig.savefig(directory / f"{name}.png", dpi=155, facecolor="#f7faf8")
    plt.close(fig)


def figure(title, xlabel="", ylabel="", figsize=(8.6, 4.8)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set(title=title, xlabel=xlabel, ylabel=ylabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.16)
    ax.set_axisbelow(True)
    return fig, ax


def report(values):
    REPORT.mkdir(exist_ok=True)
    (REPORT / "metrics.json").write_text(json.dumps(values, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(values, indent=2), flush=True)
