"""CodeEvolve — evaluate how code changes over git history."""

from codeevolve.__version__ import __version__
from codeevolve.api import CodeEvolve, EvolveReport

__all__ = ["__version__", "CodeEvolve", "EvolveReport"]
