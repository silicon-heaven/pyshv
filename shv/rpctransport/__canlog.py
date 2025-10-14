"""Logger wrapper that overwrites debug method used for can package."""

import logging


def patchlogger(logger: logging.Logger) -> None:
    setattr(logger, "debug", lambda *args, **kwargs: logger.log(9, *args, **kwargs))  # noqa: B010
    setattr(logger, "info", lambda *args, **kwargs: logger.log(9, *args, **kwargs))  # noqa: B010
