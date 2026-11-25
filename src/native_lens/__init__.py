"""native-context-lens: Governed Context Engine, Benchmark Suite & Malleable Artifact Workbench."""

from native_lens.artifacts import (
    ArtifactAccessDeniedError,
    ArtifactRuntime,
    ArtifactValidationError,
)
from native_lens.benchmark import BenchmarkRunner
from native_lens.engine import (
    DEFAULT_PERSONAS,
    AuthorizationError,
    NativeContextEngine,
    RecordNotFoundError,
)
from native_lens.models import (
    ArtifactManifest,
    BenchmarkReport,
    BlockerChainResult,
    CallerContext,
    FreshnessAlert,
    LinkModel,
    RecordModel,
)
from native_lens.vault import load_vault_into_engine

__all__ = [
    "ArtifactAccessDeniedError",
    "ArtifactManifest",
    "ArtifactRuntime",
    "ArtifactValidationError",
    "AuthorizationError",
    "BenchmarkReport",
    "BenchmarkRunner",
    "BlockerChainResult",
    "CallerContext",
    "DEFAULT_PERSONAS",
    "FreshnessAlert",
    "LinkModel",
    "NativeContextEngine",
    "RecordModel",
    "RecordNotFoundError",
    "load_vault_into_engine",
]

__version__ = "0.1.0"
