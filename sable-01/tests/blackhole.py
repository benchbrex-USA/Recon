"""Black-hole test listener: accepts connections on 8002 and never responds.

Test helper for verifying the guard's generation-timeout (504) path.
Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).
"""
import socket

s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", 8002))
s.listen(5)
print("black-hole listening on 127.0.0.1:8002 — accepting and never responding", flush=True)
conns = []
try:
    while True:
        c, addr = s.accept()
        conns.append(c)
        print(f"accepted {addr} — holding silently", flush=True)
except KeyboardInterrupt:
    pass
