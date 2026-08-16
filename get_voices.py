#!/usr/bin/env python3
"""Download the neural voice model, once, so narration can run offline.

    python get_voices.py            # English voices, ~107 MB
    python get_voices.py --all      # every language Kokoro ships, ~121 MB
    python get_voices.py --check    # what is on disk, download nothing

The system voices that ship with Windows are 2013-era concatenative synthesis
and sound it. This fetches Kokoro-82M, an open-weight neural model that runs
**in the browser on this machine** - no key, no account, no per-word cost, and
nothing leaves the machine at study time.

Three things worth being precise about, because they are the reason this script
exists rather than a `<script src=...>` tag:

* **This is the only step that touches the network, and it is a setup step.**
  Once the files are here, narration is offline exactly like the rest of the
  tool. That distinction is the whole point: `npm install` already needs the
  network, and studying still does not.
* **The model is not in git.** It is ~92 MB of weights; a repository is the
  wrong place for it, and `models/` is gitignored. Re-run this after a fresh
  clone.
* **Standard library only, and outside `drillkit/`.** The engine stays
  dependency-free. This is a separate opt-in script, which is the route
  `NARRATION-BRIEF.md` §6 named for exactly this kind of addition.

Nothing else in the tool depends on this. Skip it and narration falls back to
the system voices, which is what shipped before and still works.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request

REPO = "onnx-community/Kokoro-82M-v1.0-ONNX"
BASE = "https://huggingface.co/%s/resolve/main" % REPO

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "models", "kokoro")

# kokoro-js exposes fp32 / fp16 / q8 / q4 / q4f16. `q8` maps to this file and
# is the smallest of them - 92 MB against 305 for q4, which despite the name is
# the *largest*. On CPU it is also the fastest, which is the case that matters:
# a machine with WebGPU is not the one that needs help.
MODEL_FILE = "onnx/model_quantized.onnx"

SUPPORT = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
]

# Voice embeddings, ~510 KB each. Prefixes are language: a = American English,
# b = British. The rest are shipped by Kokoro and downloadable with --all, but
# a CISA bank is in English and 29 files is a smaller ask than 57.
ENGLISH = [
    "af.bin", "af_alloy.bin", "af_aoede.bin", "af_bella.bin", "af_heart.bin",
    "af_jessica.bin", "af_kore.bin", "af_nicole.bin", "af_nova.bin",
    "af_river.bin", "af_sarah.bin", "af_sky.bin",
    "am_adam.bin", "am_echo.bin", "am_eric.bin", "am_fenrir.bin",
    "am_liam.bin", "am_michael.bin", "am_onyx.bin", "am_puck.bin",
    "am_santa.bin",
    "bf_alice.bin", "bf_emma.bin", "bf_isabella.bin", "bf_lily.bin",
    "bm_daniel.bin", "bm_fable.bin", "bm_george.bin", "bm_lewis.bin",
]

OTHER = [
    "ef_dora.bin", "em_alex.bin", "em_santa.bin", "ff_siwis.bin",
    "hf_alpha.bin", "hf_beta.bin", "hm_omega.bin", "hm_psi.bin",
    "if_sara.bin", "im_nicola.bin",
    "jf_alpha.bin", "jf_gongitsune.bin", "jf_nezumi.bin", "jf_tebukuro.bin",
    "jm_kumo.bin",
    "pf_dora.bin", "pm_alex.bin", "pm_santa.bin",
    "zf_xiaobei.bin", "zf_xiaoni.bin", "zf_xiaoxiao.bin", "zf_xiaoyi.bin",
    "zm_yunjian.bin", "zm_yunxi.bin", "zm_yunxia.bin", "zm_yunyang.bin",
]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.0f %s" % (n, unit) if unit != "GB" else "%.1f GB" % n
        n /= 1024.0
    return "%.0f B" % n


def wanted(everything: bool):
    files = list(SUPPORT) + [MODEL_FILE]
    voices = ENGLISH + (OTHER if everything else [])
    files += ["voices/%s" % v for v in voices]
    return files


def target(rel: str) -> str:
    return os.path.join(DEST, *rel.split("/"))


def fetch(rel: str) -> bool:
    """Download one file. Returns True if it was fetched, False if already here.

    Written to a `.part` file and renamed only on success, so an interrupted
    download can never leave a truncated model that loads and then fails
    somewhere confusing.
    """
    path = target(rel)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return False

    os.makedirs(os.path.dirname(path), exist_ok=True)
    url = "%s/%s" % (BASE, rel)
    tmp = path + ".part"

    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as fh:
                while True:
                    block = response.read(262144)
                    if not block:
                        break
                    fh.write(block)
                    done += len(block)
                    if total > 1_000_000:
                        pct = 100.0 * done / total
                        sys.stdout.write("\r  %-28s %5.1f%%  %s / %s"
                                         % (rel, pct, human(done), human(total)))
                        sys.stdout.flush()
    except (urllib.error.URLError, OSError) as exc:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise SystemExit("\nCould not download %s\n  %s" % (url, exc))

    os.replace(tmp, path)
    if os.path.getsize(path) > 1_000_000:
        sys.stdout.write("\r  %-28s %5.1f%%  %s\n"
                         % (rel, 100.0, human(os.path.getsize(path))))
    return True


# The ONNX WebAssembly runtime. Not on HuggingFace - it arrives with
# `npm install` - but it belongs beside the model for the same reason: ~31 MB
# of binary that has to be served locally, because transformers.js otherwise
# points at a CDN and every cold start would pull it down.
RUNTIME_FILES = [
    "ort-wasm-simd-threaded.wasm",
    "ort-wasm-simd-threaded.mjs",
    "ort-wasm-simd-threaded.jsep.wasm",
    "ort-wasm-simd-threaded.jsep.mjs",
]

# phonemizer is copied here for a different reason: not size, but because
# bundling breaks it. It embeds espeak-ng as an Emscripten module, and the
# minifier leaves espeak with an empty language table - every call then fails
# with `Invalid language identifier: "en-us"`. The identical file served
# untouched works first time, so the front end imports it from here at runtime.
# See frontend/src/lib/phonemizer-shim.ts.
PHONEMIZER = "phonemizer.js"

RUNTIME_SRC = os.path.join(HERE, "frontend", "node_modules", "onnxruntime-web", "dist")
PHONEMIZER_SRC = os.path.join(HERE, "frontend", "node_modules", "phonemizer", "dist")
RUNTIME_DEST = os.path.join(HERE, "models", "runtime")


def copy_runtime() -> int:
    """Copy the ONNX runtime next to the model. Returns files copied."""
    if not os.path.isdir(RUNTIME_SRC):
        print("  not found - run 'npm install' in frontend/, then re-run this")
        print("  script. Narration falls back to the system voices until then.")
        return 0

    os.makedirs(RUNTIME_DEST, exist_ok=True)
    copied = 0
    for name in RUNTIME_FILES + [PHONEMIZER]:
        source = os.path.join(
            PHONEMIZER_SRC if name == PHONEMIZER else RUNTIME_SRC, name)
        dest = os.path.join(RUNTIME_DEST, name)
        if not os.path.isfile(source):
            continue
        if os.path.exists(dest) and os.path.getsize(dest) == os.path.getsize(source):
            continue
        with open(source, "rb") as fin, open(dest, "wb") as fout:
            while True:
                block = fin.read(1 << 20)
                if not block:
                    break
                fout.write(block)
        copied += 1
        print("  %-34s %s" % (name, human(os.path.getsize(dest))))
    return copied


def runtime_ready() -> bool:
    return all(os.path.isfile(os.path.join(RUNTIME_DEST, n))
               for n in (RUNTIME_FILES[0], RUNTIME_FILES[1], PHONEMIZER))


def report(files) -> int:
    present = [f for f in files if os.path.exists(target(f))]
    missing = [f for f in files if f not in present]
    size = sum(os.path.getsize(target(f)) for f in present)

    print("Model directory: %s" % DEST)
    print("  %d of %d files present, %s on disk"
          % (len(present), len(files), human(size)))
    if missing:
        print("  missing: %d file(s)" % len(missing))
        for name in missing[:5]:
            print("    - %s" % name)
        if len(missing) > 5:
            print("    ... and %d more" % (len(missing) - 5))
        print("\nRun 'python get_voices.py' to fetch them.")
    elif not runtime_ready():
        print("  ONNX runtime: MISSING")
        print("\nWeights are here but the runtime is not. Run 'npm install' in")
        print("frontend/, then re-run this script.")
    else:
        print("  ONNX runtime: present")
        print("\nComplete. Open the web app, turn narration on, and choose the")
        print("neural engine in the voice settings.")
    return 0 if (not missing and runtime_ready()) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Download the offline neural voice model for narration.")
    parser.add_argument("--all", action="store_true",
                        help="every language, not just English (~14 MB more)")
    parser.add_argument("--check", action="store_true",
                        help="report what is on disk and exit")
    args = parser.parse_args(argv)

    files = wanted(args.all)
    if args.check:
        return report(files)

    print("Kokoro-82M neural voices")
    print("  from https://huggingface.co/%s" % REPO)
    print("  into %s" % DEST)
    print("  %d files, roughly %s"
          % (len(files), human(92_000_000 + len(files) * 510_000)))
    print()
    print("This is a one-time setup download. Narration itself runs offline,")
    print("in the browser, and sends nothing anywhere.")
    print()

    fetched = 0
    for rel in files:
        if fetch(rel):
            fetched += 1
        elif not rel.endswith(".onnx"):
            pass

    print()
    if fetched:
        print("Downloaded %d file(s)." % fetched)
    else:
        print("Everything was already present.")

    print()
    print("ONNX runtime:")
    copied = copy_runtime()
    if copied:
        print("  copied %d file(s) from frontend/node_modules" % copied)
    elif runtime_ready():
        print("  already present")

    print()
    return report(files)


if __name__ == "__main__":
    sys.exit(main())
