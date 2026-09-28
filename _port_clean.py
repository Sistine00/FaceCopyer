import subprocess

ADDR = ":7860"

def main():
    try:
        out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, encoding="oem", errors="ignore").stdout
    except Exception:
        return
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and ADDR in parts[1] and parts[3].upper() == "LISTENING":
            pids.add(parts[4])
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/pid", str(pid), "/f"], capture_output=True, timeout=10)
            print("[INFO] Port 7860 in use (PID {}), stopped old process.".format(pid))
        except Exception:
            continue

if __name__ == "__main__":
    main()