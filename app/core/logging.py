import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

# Context variable to hold trace ID across async coroutines
trace_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default=None)


def get_trace_id() -> Optional[str]:
    return trace_id_ctx.get()


def set_trace_id(trace_id: Optional[str] = None) -> str:
    tid = trace_id or str(uuid.uuid4())
    trace_id_ctx.set(tid)
    return tid


class StructuredJsonFormatter(logging.Formatter):
    """Outputs log records as single-line JSON formatted strings (Pino/CloudWatch compatible)."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "level": record.levelname.lower(),
            "time": datetime.now(timezone.utc).isoformat(),
            "pid": record.process,
            "name": record.name,
            "msg": record.getMessage(),
        }

        # Include traceId if present in context
        tid = get_trace_id()
        if tid:
            log_data["traceId"] = tid

        # Extract extra fields passed to logger
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_data.update(record.extra_fields)

        # Include exception details if present
        if record.exc_info:
            log_data["err"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Error",
                "message": str(record.exc_info[1]),
                "stack": self.formatException(record.exc_info),
            }

        return json.dumps(log_data, default=str)


class StructuredLogger:
    """Wrapper around standard Logger supporting dictionary/keyword structured arguments."""

    def __init__(self, name: str = "app"):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(StructuredJsonFormatter())
            self._logger.addHandler(handler)
            self._logger.propagate = False

    def _log(
        self,
        level: int,
        msg: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
        **kwargs: Any,
    ) -> None:
        combined_extra = {}
        if extra:
            combined_extra.update(extra)
        if kwargs:
            combined_extra.update(kwargs)

        self._logger.log(
            level,
            msg,
            exc_info=exc_info,
            extra={"extra_fields": combined_extra} if combined_extra else None,
        )

    def debug(self, msg: str = "", extra: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, extra, **kwargs)

    def info(self, msg: str = "", extra: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, extra, **kwargs)

    def warn(self, msg: str = "", extra: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, extra, **kwargs)

    def warning(self, msg: str = "", extra: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, extra, **kwargs)

    def error(
        self,
        msg: str = "",
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
        **kwargs: Any,
    ) -> None:
        self._log(logging.ERROR, msg, extra, exc_info=exc_info, **kwargs)


logger = StructuredLogger("line-ghl-middleware")
