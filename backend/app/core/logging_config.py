import logging


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Audit events are always worth keeping regardless of the root logger's level.
    logging.getLogger("newsatlas.audit").setLevel(logging.INFO)
