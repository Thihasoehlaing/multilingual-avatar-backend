import logging
import sys
from contextvars import ContextVar

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"
        return True

def get_logger(name: str = "app"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s %(name)s req=%(request_id)s: %(message)s'
        )
        handler.setFormatter(formatter)
        handler.addFilter(RequestIdFilter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger

logger = get_logger()
