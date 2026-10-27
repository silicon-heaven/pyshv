"""Logger wrapper that overwrites debug method used for can package."""

import logging


def patchlogger(logger: logging.Logger) -> None:
    setattr(logger, "debug", lambda *args, **kwargs: logger.log(9, *args, **kwargs))  # ruff: ignore[set-attr-with-constant]
    setattr(logger, "info", lambda *args, **kwargs: logger.log(9, *args, **kwargs))  # ruff: ignore[set-attr-with-constant]
