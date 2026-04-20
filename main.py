import subprocess, sys, signal, os

base = os.path.dirname(os.path.abspath(__file__))
server_process = None
app_process = None


def signal_handler(sig, frame):
    print("\n正在关闭服务...")
    if server_process:
        server_process.terminate()
    if app_process:
        app_process.terminate()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

print("启动服务...")
app_process = subprocess.Popen([sys.executable, base + "\\app\\main.py"])

print("按 Ctrl+C 停止服务")
app_process.wait()
