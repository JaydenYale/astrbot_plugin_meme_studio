try:
    from .meme_studio.renderer import *  # noqa: F401,F403
except ImportError:
    from meme_studio.renderer import *  # noqa: F401,F403
