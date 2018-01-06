
try:
    from .version import __version__
except ImportError:
    __version__ = 'master'

from .parse import batch_convert
