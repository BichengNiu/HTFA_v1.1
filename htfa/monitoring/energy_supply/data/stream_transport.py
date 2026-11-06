"""Optional server-side websocket transport, independent of processing rules."""

try:
    from websockets.sync.client import connect as websocket_connect
except ImportError:
    websocket_connect = None
