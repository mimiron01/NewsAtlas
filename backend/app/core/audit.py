import logging

audit_logger = logging.getLogger("newsatlas.audit")


def log_event(event: str, request=None, **fields: object) -> None:
    """Structured-ish audit log line. Never pass passwords, tokens, or secrets in fields."""
    if request is not None:
        fields.setdefault("ip", getattr(getattr(request, "client", None), "host", "unknown"))
    parts = " ".join(f"{key}={value}" for key, value in fields.items())
    audit_logger.info("%s %s", event, parts)
