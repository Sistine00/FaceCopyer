import os
import socket
import subprocess
import time

IOPAINT_VENV = r'D:\facefusion\iopaint_venv'
IOPAINT_EXE = os.path.join(IOPAINT_VENV, r'Scripts\iopaint.exe')
IOPAINT_PYTHON = os.path.join(IOPAINT_VENV, r'Scripts\python.exe')
MODEL_DIR = r'D:\facefusion\iopaint_models'
PORT = 8081
LOG = r'D:\facefusion\iopaint_runtime.log'


def is_port_open(port : int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(1)
            s.connect(('127.0.0.1', port))
            return True
        except Exception:
            return False


def detect_device() -> str:
    requested = os.environ.get('IOPAINT_DEVICE', 'auto').strip().lower()
    if requested in ( 'cpu', 'cuda' ):
        return requested
    try:
        result = subprocess.run(
            [ IOPAINT_PYTHON, '-c', 'import torch; print("cuda" if torch.cuda.is_available() else "cpu")' ],
            capture_output = True,
            text = True,
            timeout = 60
        )
        detected = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ''
        if detected in ( 'cpu', 'cuda' ):
            return detected
    except Exception:
        pass
    return 'cpu'


def launch(device : str, env : dict, log_handle) -> object:
    args = [
        IOPAINT_EXE, 'start',
        '--host', '127.0.0.1',
        '--port', str(PORT),
        '--model', 'lama',
        '--model-dir', MODEL_DIR,
        '--no-inbrowser',
        '--device', device,
    ]
    process = subprocess.Popen(args, env = env, stdout = log_handle, stderr = subprocess.STDOUT, cwd = r'D:\facefusion', creationflags = subprocess.CREATE_NO_WINDOW)
    for _ in range(60):
        time.sleep(1)
        if is_port_open(PORT):
            return process
        if process.poll() is not None:
            return None
    # still alive but never served: kill it so the fallback attempt can bind the port
    process.terminate()
    try:
        process.wait(timeout = 10)
    except Exception:
        process.kill()
    time.sleep(2)
    return None


def main() -> None:
    if is_port_open(PORT):
        print('IOPaint already running on port {}'.format(PORT))
        return

    model_file = os.path.join(MODEL_DIR, 'torch', 'hub', 'checkpoints', 'big-lama.pt')
    env = dict(os.environ)
    env['LAMA_MODEL_URL'] = model_file
    env['HF_HUB_CACHE'] = os.path.join(MODEL_DIR, 'hub')

    device = detect_device()
    print('[INFO] IOPaint device: {}'.format(device))

    log_handle = open(LOG, 'a', encoding = 'utf-8', buffering = 1)
    process = launch(device, env, log_handle)

    if process is None and device == 'cuda':
        print('[WARN] IOPaint failed to start on CUDA, falling back to CPU')
        if is_port_open(PORT):
            print('[INFO] IOPaint already running on port {}'.format(PORT))
            return
        process = launch('cpu', env, log_handle)
        device = 'cpu'

    if process is not None:
        print('IOPaint started on port {} ({})'.format(PORT, device))
    else:
        print('IOPaint failed to start, see {}'.format(LOG))


if __name__ == '__main__':
    main()
