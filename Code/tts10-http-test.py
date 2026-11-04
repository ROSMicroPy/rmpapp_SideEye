import socket
import time

HOST = "192.168.4.1"  # Change to your TTS-10 IP
PORT = 8080

sock = socket.create_connection((HOST, PORT), timeout=5)
sock.settimeout(0.5)

def read_response(timeout=3):
    lines = []
    pending = b""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            data = sock.recv(4096)
            if not data:
                break
            pending += data

            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                line = line.decode(errors="replace").strip()
                if not line:
                    continue

                print("  ", line)
                lines.append(line)

                if line == "ok" or line.startswith("error:"):
                    return lines

        except socket.timeout:
            continue

    return lines

def send_command(command):
    print("Sending:", command)
    sock.sendall((command + "\n").encode())
    return read_response()

# Drain startup messages
time.sleep(0.5)
sock.setblocking(False)
try:
    while sock.recv(4096):
        pass
except BlockingIOError:
    pass
finally:
    sock.setblocking(True)
    sock.settimeout(0.5)

X=0
Y=230
speed=150
send_command("G0 X0 Y230")

while Y>100:
    if X == 0: X = 250
    else: X=0

    send_command(f"G1 X{X} Y{Y} F{speed}")
    time.sleep(2 * 60)
    Y = Y-10

sock.close()
