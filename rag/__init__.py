"""RAG package.

Import-order and OpenMP workarounds for macOS:

faiss-cpu and torch each bundle their own OpenMP runtime. On macOS, importing
faiss before torch (or letting both run multi-threaded) intermittently
segfaults the process. Importing torch first and pinning duplicate-lib
tolerance makes the combination stable; both are no-ops on Linux.
"""

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import torch  # noqa: F401, E402  (must load before faiss — see docstring)
