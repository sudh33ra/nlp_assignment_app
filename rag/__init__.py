"""RAG package.

On macOS, faiss-cpu and torch each bundle their own OpenMP runtime, and
loading both crashes the process. Setting KMP_DUPLICATE_LIB_OK before either
library is imported is the standard workaround; it is a no-op elsewhere.
"""

import os

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
