"""WebSocket caller for the endpoint under test.

Holds one persistent connection per test run:
  ws = WebSocketSession(endpoint, run_id=run_id)
  await ws.connect()
  result = await ws.send_and_receive(payload)   # called once per turn
  await ws.close()

Features:
- Protocol-level ping disabled (ping_interval=None): many servers (e.g. Supabase
  Edge Functions) do not respond to WebSocket ping frames, so the library default
  of ping_interval=20 / ping_timeout=20 would spuriously close healthy idle
  connections. We set both to None and rely on application-level keepalive instead.
- Application-level ping/pong: JSON frames with {"type":"ping"} are answered with
  {"type":"pong"} and skipped; {"type":"pong"} responses are silently discarded.
- Auto-reconnect: if the connection is found closed before or during a turn
  (ConnectionClosed), the session reconnects once and retries the full exchange.
- asyncio.Lock: guards send_and_receive so concurrent callers never interleave frames.
- Run-scoped logging: every connect/send/recv/error event is appended to the
  in-memory log store (backend.services.run_log) for the UI logs panel.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from backend.models.endpoint_config import EndpointConfig
from backend.services.endpoint_caller import EndpointCallResult, _apply_auth
from backend.services.run_log import ws_log

logger = logging.getLogger(__name__)

# Application-level message types to silently skip in the receive loop.
_SKIP_APP_TYPES = frozenset({"pong"})


class WebSocketSession:
    """Persistent WebSocket connection for one test run."""

    def __init__(self, config: EndpointConfig, *, run_id: int = 0) -> None:
        self._config = config
        self._run_id = run_id
        self._ws: Any = None
        self._open = False   # our own flag; avoids false-negatives from ws.closed
        self._lock = asyncio.Lock()  # one in-flight exchange at a time
        self._keepalive_task: asyncio.Task | None = None

    # ── connection state ────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        # Use our own _open flag rather than self._ws.closed.
        # Several websockets versions return closed=True on a freshly opened
        # connection before the first send, producing a spurious reconnect.
        # We set _open ourselves on success and clear it on close/error.
        return self._open and self._ws is not None

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        import websockets  # type: ignore[import]

        headers = _apply_auth(
            dict(self._config.headers or {}),
            self._config.auth_type,
            self._config.auth_value,
        )
        header_list = list(headers.items())
        timeout = float(self._config.timeout_seconds)

        # Disable the library's built-in ping/pong keepalive.
        # Many servers (e.g. Supabase Edge Functions) do not respond to WebSocket
        # ping frames, so the library's default ping_interval=20 / ping_timeout=20
        # would close perfectly healthy connections after ~40 s of inactivity.
        # Instead we rely on application-level ping/pong (JSON {"type":"ping"})
        # and the auto-reconnect logic in _exchange to handle stale connections.
        ws_kwargs: dict[str, Any] = {
            "ping_interval": None,
            "ping_timeout": None,
        }

        # websockets >= 14 uses additional_headers; 12/13 used extra_headers.
        exc_last: Exception | None = None
        for header_kwarg in ("additional_headers", "extra_headers"):
            try:
                self._ws = await asyncio.wait_for(
                    websockets.connect(
                        self._config.url,
                        **{header_kwarg: header_list},
                        **ws_kwargs,
                    ),
                    timeout=timeout,
                )
                self._open = True
                ws_log(self._run_id, "event", "connect",
                       f"Connected to {self._config.url}")
                logger.debug("WebSocket connected: %s", self._config.url)
                return
            except TypeError as exc:
                exc_last = exc
                continue  # try the other kwarg name
            except Exception as exc:
                ws_log(self._run_id, "event", "error",
                       f"Connection failed: {exc}")
                raise

        # Last resort: connect without custom headers
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(self._config.url, **ws_kwargs),
                timeout=timeout,
            )
            self._open = True
            ws_log(self._run_id, "event", "connect",
                   f"Connected to {self._config.url} (no custom headers)")
        except Exception as exc:
            ws_log(self._run_id, "event", "error", f"Connection failed: {exc}")
            raise

    async def reconnect(self) -> None:
        """Close the current connection and open a new one."""
        ws_log(self._run_id, "event", "reconnect",
               f"Reconnecting to {self._config.url}…")
        logger.info("WebSocket reconnecting to %s", self._config.url)
        await self.close()
        await self.connect()

    # ── post-connect drain ───────────────────────────────────────────────────

    async def drain(self, timeout: float) -> None:
        """Read and discard all messages arriving within *timeout* seconds.

        Call this once right after connect() to consume any server-sent welcome
        frames before the first user message is sent.  Messages are logged as
        "discard" so they appear in the WS logs panel but are clearly marked.
        Responds to application-level pings during the window so the server
        does not close the connection.
        """
        if timeout <= 0:
            return

        import websockets  # type: ignore[import]

        ws_log(self._run_id, "event", "connect",
               f"Draining welcome frames for {timeout:.1f}s…")
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
                raw_str = (raw if isinstance(raw, str)
                           else raw.decode("utf-8", errors="replace"))
                # Respond to app-level pings so the server doesn't close us.
                try:
                    data = json.loads(raw_str)
                    if isinstance(data, dict) and (data.get("type") or "").lower() == "ping":
                        pong = json.dumps({"type": "pong"})
                        await self._ws.send(pong)
                        ws_log(self._run_id, "out", "pong", pong)
                        continue
                except (json.JSONDecodeError, Exception):
                    pass
                ws_log(self._run_id, "in", "discard", raw_str)
            except asyncio.TimeoutError:
                break
            except websockets.exceptions.ConnectionClosed:
                self._open = False
                break
            except asyncio.CancelledError:
                raise
            except Exception:
                break
        ws_log(self._run_id, "event", "connect", "Drain complete — ready to send")

    # ── keepalive (step-mode pauses) ─────────────────────────────────────────

    def start_keepalive(self) -> None:
        """Spawn a background task to respond to server pings while paused."""
        if self._keepalive_task and not self._keepalive_task.done():
            return
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def stop_keepalive(self) -> None:
        """Cancel and await the keepalive task.

        Call this before send_and_receive() to ensure no concurrent recv() calls.
        """
        task = self._keepalive_task
        self._keepalive_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _keepalive_loop(self) -> None:
        """Read frames and respond to application-level pings to keep the server
        from closing an idle connection during a step-mode pause."""
        import websockets  # type: ignore[import]

        while True:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=10.0)
                try:
                    data = json.loads(raw) if isinstance(raw, (str, bytes)) else None
                except (json.JSONDecodeError, TypeError):
                    data = None

                raw_str = (raw if isinstance(raw, str)
                           else raw.decode("utf-8", errors="replace"))

                if isinstance(data, dict) and (data.get("type") or "").lower() == "ping":
                    ws_log(self._run_id, "in", "ping", raw_str)
                    async with self._lock:
                        pong = json.dumps({"type": "pong"})
                        try:
                            await self._ws.send(pong)
                            ws_log(self._run_id, "out", "pong", pong)
                        except Exception:
                            pass

            except asyncio.TimeoutError:
                continue  # nothing received; keep watching
            except websockets.exceptions.ConnectionClosed:
                self._open = False
                break
            except asyncio.CancelledError:
                break
            except Exception:
                break

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self.stop_keepalive()
        self._open = False
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
            ws_log(self._run_id, "event", "disconnect", "Connection closed")

    # ── send / receive ────────────────────────────────────────────────────────

    async def send_and_receive(self, payload: Any) -> EndpointCallResult:
        """Send *payload* and wait for the first non-ping/pong reply.

        Handles two passes of resilience:
        1. If the connection is detected closed before sending → reconnect, then send.
        2. If ConnectionClosed is raised during send/recv → reconnect once, retry.
        """
        async with self._lock:
            return await self._exchange(payload, allow_reconnect=True)

    async def _exchange(self, payload: Any, *, allow_reconnect: bool) -> EndpointCallResult:
        import websockets  # type: ignore[import]

        # Reconnect proactively if we know the socket is gone.
        if not self.is_connected:
            if not allow_reconnect:
                ws_log(self._run_id, "event", "error", "Not connected — send aborted")
                return EndpointCallResult(
                    status_code=None, response_json=None, response_text="",
                    latency_ms=0, error="WebSocket not connected", retries_used=0,
                )
            ws_log(self._run_id, "event", "reconnect",
                   "Connection lost before send; reconnecting…")
            logger.warning("WebSocket not connected before send; reconnecting…")
            try:
                await self.reconnect()
            except Exception as exc:
                ws_log(self._run_id, "event", "error",
                       f"Reconnect failed: {exc}")
                return EndpointCallResult(
                    status_code=None, response_json=None, response_text="",
                    latency_ms=0,
                    error=f"WebSocket reconnect failed: {exc}",
                    retries_used=1,
                )

        message = json.dumps(payload) if not isinstance(payload, str) else payload
        timeout = float(self._config.timeout_seconds)
        t0 = time.monotonic()

        try:
            ws_log(self._run_id, "out", "message", message)
            await self._ws.send(message)

            # Receive loop: discard application-level ping/pong; return on first
            # real message. Protocol-level pings are handled transparently by the
            # websockets library and never appear here.
            while True:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
                latency_ms = int((time.monotonic() - t0) * 1000)

                try:
                    data = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                except (json.JSONDecodeError, TypeError):
                    data = None

                raw_str = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")

                if isinstance(data, dict):
                    msg_type = (data.get("type") or "").lower()
                    if msg_type == "ping":
                        ws_log(self._run_id, "in",  "ping", raw_str)
                        try:
                            pong = json.dumps({"type": "pong"})
                            await self._ws.send(pong)
                            ws_log(self._run_id, "out", "pong", pong)
                        except Exception:
                            pass
                        continue
                    if msg_type in _SKIP_APP_TYPES:
                        ws_log(self._run_id, "in", "pong", raw_str)
                        continue

                ws_log(self._run_id, "in", "message", raw_str)
                return EndpointCallResult(
                    status_code=101,  # 101 Switching Protocols = active WS
                    response_json=data,
                    response_text=raw_str,
                    latency_ms=latency_ms,
                    error=None,
                    retries_used=0,
                )

        except websockets.exceptions.ConnectionClosed as exc:
            self._open = False
            elapsed = int((time.monotonic() - t0) * 1000)
            ws_log(self._run_id, "event", "disconnect",
                   f"Connection closed during exchange: {exc}")
            logger.warning("WebSocket closed during exchange: %s", exc)
            if allow_reconnect:
                ws_log(self._run_id, "event", "reconnect",
                       "Reconnecting after closed connection…")
                try:
                    await self.reconnect()
                    logger.info("Reconnected; retrying exchange…")
                    return await self._exchange(payload, allow_reconnect=False)
                except Exception as reconn_exc:
                    ws_log(self._run_id, "event", "error",
                           f"Reconnect failed: {reconn_exc}")
                    return EndpointCallResult(
                        status_code=None, response_json=None, response_text="",
                        latency_ms=elapsed,
                        error=f"WebSocket closed and reconnect failed: {reconn_exc}",
                        retries_used=1,
                    )
            return EndpointCallResult(
                status_code=None, response_json=None, response_text="",
                latency_ms=elapsed,
                error=f"WebSocket closed: {exc}",
                retries_used=0,
            )

        except asyncio.TimeoutError:
            ws_log(self._run_id, "event", "error",
                   f"Recv timed out after {self._config.timeout_seconds}s")
            return EndpointCallResult(
                status_code=None, response_json=None, response_text="",
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=f"WebSocket recv timed out after {self._config.timeout_seconds}s",
                retries_used=0,
            )

        except Exception as exc:
            ws_log(self._run_id, "event", "error", f"{type(exc).__name__}: {exc}")
            return EndpointCallResult(
                status_code=None, response_json=None, response_text="",
                latency_ms=int((time.monotonic() - t0) * 1000),
                error=f"{type(exc).__name__}: {exc}",
                retries_used=0,
            )

    # ── context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "WebSocketSession":
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
