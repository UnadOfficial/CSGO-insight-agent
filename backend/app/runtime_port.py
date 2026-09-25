"""Single source of truth for the local backend HTTP port.

Three independent consumers must agree on one number:

* the uvicorn listener (``run_server``),
* the Game State Integration sink URL written into
  ``gamestate_integration_*.cfg`` (``obs_director._resolve_gsi_sink_url``),
* every launcher that opens the browser at the backend URL.

They previously carried separate defaults (19871 for the listener, 8000 for the
GSI sink).  A launcher that did not export ``CSGO_INSIGHT_PORT`` therefore
pointed CS:GO's GSI at a port nothing was listening on: the game started fine,
but ``is_gsi_ready()`` never became true and recording aborted after the full
120 s gate with ``RECORDING_GSI_NOT_READY`` ("CS:GO 未在限定时间内进入游戏画面").
Keeping the default in one place — and exporting it from every launcher —
removes that class of mismatch.
"""

from __future__ import annotations

import os

#: Port used when ``CSGO_INSIGHT_PORT`` is unset or unusable.
DEFAULT_BACKEND_PORT = 19871

#: Environment variable that overrides :data:`DEFAULT_BACKEND_PORT`.
ENV_PORT = "CSGO_INSIGHT_PORT"


def resolve_backend_port() -> int:
    """Return the backend HTTP port every component must agree on.

    Falls back to :data:`DEFAULT_BACKEND_PORT` for an unset, non-numeric or
    out-of-range value, so a malformed environment variable can neither desync
    the GSI sink from the listener nor hand uvicorn an unusable port.
    """
    raw = (os.environ.get(ENV_PORT) or "").strip()
    if not raw:
        return DEFAULT_BACKEND_PORT
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_BACKEND_PORT
    if 1 <= port <= 65535:
        return port
    return DEFAULT_BACKEND_PORT
