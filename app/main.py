import asyncio
import websockets
import pyautogui
import win32api
import win32con
import win32clipboard
import socket
import json
import time
import os
import base64
import sys
import threading
import secrets
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from flask import Flask, render_template, jsonify, request, abort
import qrcode
from io import BytesIO
import webbrowser
from PIL import Image, ImageDraw
import pystray

# 确定模板目录（支持PyInstaller打包）
def get_template_dir():
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
        return os.path.join(base_path, "server", "templates")
    else:
        return os.path.join(os.path.dirname(__file__), "..", "server", "templates")


app = Flask(__name__, template_folder=get_template_dir())

size = pyautogui.size()
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0
alt = False

# 文件上传相关
def get_runtime_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


RUNTIME_DIR = get_runtime_dir()
CONFIG_FILE = RUNTIME_DIR / "settings.json"
uploading_files = {}
UPLOAD_DIR = RUNTIME_DIR / "uploaded_files"
UPLOAD_DIR_RESOLVED = UPLOAD_DIR.resolve()


def set_upload_dir(path_str):
    global UPLOAD_DIR, UPLOAD_DIR_RESOLVED
    target = Path(path_str).expanduser()
    if not target.is_absolute():
        raise ValueError("路径必须为绝对路径")
    target.mkdir(parents=True, exist_ok=True)
    if not target.is_dir():
        raise ValueError("路径不是有效目录")
    if not os.access(target, os.W_OK):
        raise ValueError("目录不可写")
    UPLOAD_DIR = target
    UPLOAD_DIR_RESOLVED = target.resolve()


def load_settings():
    if not CONFIG_FILE.exists():
        set_upload_dir(str(RUNTIME_DIR / "uploaded_files"))
        return
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        saved_dir = data.get("upload_dir")
        if saved_dir:
            set_upload_dir(saved_dir)
        else:
            set_upload_dir(str(RUNTIME_DIR / "uploaded_files"))
    except Exception:
        set_upload_dir(str(RUNTIME_DIR / "uploaded_files"))


def save_settings():
    payload = {"upload_dir": str(UPLOAD_DIR_RESOLVED)}
    CONFIG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
WS_TOKEN = secrets.token_urlsafe(16)

# 系统托盘相关
import pystray
from PIL import Image, ImageDraw
tray_icon = None
client_connected = False  # 全局连接状态


def update_tray_icon(connected):
    """更新托盘图标（连接状态变化时调用）"""
    global tray_icon, client_connected
    client_connected = connected
    
    try:
        if tray_icon is not None:
            # 重新创建图标
            def create_tray_image(connected=False):
                """根据连接状态创建托盘图标"""
                size = 64
                color = "#2ecc71" if connected else "#e74c3c"  # 绿色=连接，红色=断开
                image = Image.new('RGB', (size, size), color)
                draw = ImageDraw.Draw(image)
                
                # 画一个圆角矩形（触控板形状）
                margin = 12
                draw.rounded_rectangle(
                    [margin, margin, size-margin, size-margin],
                    radius=8,
                    outline='white',
                    width=3
                )
                
                # 画状态指示
                if connected:
                    # 连接状态：中间一个圆点
                    center = size // 2
                    draw.ellipse([center-6, center-6, center+6, center+6], fill='white')
                else:
                    # 断开状态：画一个叉
                    draw.line([(20, 20), (44, 44)], fill='white', width=3)
                    draw.line([(44, 20), (20, 44)], fill='white', width=3)
                
                return image
            
            icon_img = create_tray_image(connected)
            tray_icon.icon = icon_img
            tray_icon.title = f"无线触控板 - {'已连接' if connected else '未连接'}"
            print(f"[*] 托盘图标已更新: {'连接' if connected else '断开'}", flush=True)
    except Exception as e:
        print(f"[!] 更新托盘图标失败: {e}", flush=True)


def create_tray_icon():
    """创建系统托盘图标（使用pystray库）"""
    global tray_icon, client_connected
    
    try:
        print("[*] 使用pystray创建托盘...", flush=True)
        
        # 创建托盘图标图像
        def create_tray_image(connected=False):
            """根据连接状态创建托盘图标"""
            size = 64
            color = "#2ecc71" if connected else "#e74c3c"  # 绿色=连接，红色=断开
            image = Image.new('RGB', (size, size), color)
            draw = ImageDraw.Draw(image)
            
            # 画一个圆角矩形（触控板形状）
            margin = 12
            draw.rounded_rectangle(
                [margin, margin, size-margin, size-margin],
                radius=8,
                outline='white',
                width=3
            )
            
            # 画一个圆点表示连接状态
            if connected:
                # 连接状态：中间一个绿点
                center = size // 2
                draw.ellipse([center-6, center-6, center+6, center+6], fill='white')
            else:
                # 断开状态：画一个叉
                draw.line([(20, 20), (44, 44)], fill='white', width=3)
                draw.line([(44, 20), (20, 44)], fill='white', width=3)
            
            return image
        
        # 打开浏览器函数
        def open_browser_tray(icon=None, item=None):
            try:
                ip = socket.gethostbyname(socket.gethostname())
                webbrowser.open(f"http://{ip}:5000/connect")
            except Exception as e:
                print(f"[!] 打开浏览器失败: {e}")
        
        # 退出函数
        def exit_app(icon, item):
            os._exit(0)
        
        # 创建菜单
        menu = pystray.Menu(
            pystray.MenuItem("打开连接页面", open_browser_tray, default=True),
            pystray.MenuItem("退出", exit_app)
        )
        
        # 创建图标
        icon_img = create_tray_image(client_connected)
        tray_icon = pystray.Icon(
            "无线触控板",
            icon_img,
            f"无线触控板 - {'已连接' if client_connected else '未连接'}",
            menu
        )
        
        print("[*] 系统托盘图标已创建", flush=True)
        
        # 写入标记文件（调试用）
        try:
            with open("tray_ready.txt", "w") as f:
                f.write("ready")
        except:
            pass
        
        print("[*] 准备运行托盘（tray_icon.run()...）", flush=True)
        # 运行托盘（这会阻塞，所以在独立线程中）
        tray_icon.run()
        print("[*] 托盘运行结束", flush=True)
        
    except Exception as e:
        print(f"[!] 托盘创建失败: {e}", flush=True)
        import traceback
        traceback.print_exc()


def open_browser():
    """打开浏览器"""
    try:
        ip = socket.gethostbyname(socket.gethostname())
        url = f"http://{ip}:5000/connect"  # 电脑端连接页面
        webbrowser.open(url)
    except Exception as e:
        print(f"[!] 打开浏览器失败: {e}")


def type_with_clipboard(text, backspace_count=0):
    print(f"text: '{text}', backspace: {backspace_count}")
    old_text = ""
    try:
        win32clipboard.OpenClipboard()
        old_text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
    except:
        pass
    finally:
        try:
            win32clipboard.CloseClipboard()
        except:
            pass

    if backspace_count > 0:
        for _ in range(backspace_count):
            pyautogui.press("backspace")
            time.sleep(0.02)

    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
        win32clipboard.CloseClipboard()
    except Exception as e:
        print(f"clipboard error: {e}")
        return

    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.05)

    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, old_text)
        win32clipboard.CloseClipboard()
    except:
        pass


async def handle_client(websocket):
    global alt, client_connected
    request_path = getattr(websocket, "path", "")
    if not request_path and hasattr(websocket, "request"):
        request_path = getattr(websocket.request, "path", "")
    parsed = urlparse(request_path or "")
    received_token = parse_qs(parsed.query).get("token", [None])[0]
    if received_token != WS_TOKEN:
        print(f"[!] 拒绝未授权WebSocket连接, path={request_path!r}")
        await websocket.close(code=1008, reason="unauthorized")
        return

    print("\n====== 客户端已连接 ======")
    
    # 更新托盘图标为连接状态
    update_tray_icon(True)
    
    try:
        async for raw_message in websocket:
            try:
                msg = json.loads(raw_message)
            except Exception as e:
                print(f"JSON解析错误: {e}")
                continue

            if key := msg.get("key", None):
                if isinstance(key, (tuple, list)):
                    text = key[0]
                    backspace_count = key[1] if len(key) > 1 else 0
                    type_with_clipboard(text, backspace_count)
                else:
                    pyautogui.press(key)

            elif hotkey := msg.get("hotkey", None):
                pyautogui.hotkey(*hotkey)

            elif coords := msg.get("touch", None):
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_MOVE,
                    int(coords[0] * size[0]),
                    int(coords[1] * size[1]),
                )

            elif msg.get("tap", None):
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)

            elif msg.get("rightTap", None):
                win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0)
                win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0)

            elif scroll := msg.get("scroll", None):
                if isinstance(scroll, (list, tuple)) and len(scroll) >= 2:
                    vertical_scroll = int(scroll[1] * 10)
                    if vertical_scroll != 0:
                        pyautogui.scroll(vertical_scroll)

            elif msg.get("drag", None):
                if msg.get("start", None):
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0)
                elif msg.get("end", None):
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0)

            elif msg.get("media_volume_up", None):
                pyautogui.press("volumeup")

            elif msg.get("media_volume_down", None):
                pyautogui.press("volumedown")

            elif msg.get("media_volume_mute", None):
                pyautogui.press("volumemute")

            elif msg.get("media_play_pause", None):
                pyautogui.press("playpause")

            elif msg.get("media_next", None):
                pyautogui.press("nexttrack")

            elif msg.get("media_prev", None):
                pyautogui.press("prevtrack")

            elif file_meta := msg.get("file_meta", None):
                filename = file_meta.get("name", f"upload_{int(time.time())}")
                filename = os.path.basename(str(filename)).replace("\x00", "")
                if not filename:
                    filename = f"upload_{int(time.time())}"
                file_size = file_meta.get("size", 0)
                base, ext = os.path.splitext(filename)
                unique_name = f"{base}_{int(time.time() * 1000)}{ext}"
                filepath = (UPLOAD_DIR / unique_name).resolve()
                if not str(filepath).startswith(str(UPLOAD_DIR_RESOLVED) + os.sep):
                    print(f"[!] 非法文件路径: {filepath}")
                    continue
                f = open(filepath, "wb")
                uploading_files[filename] = {
                    "file_handle": f,
                    "total": file_size,
                    "received": 0,
                    "filepath": filepath,
                }
                print(f"开始接收文件: {filename}")

            elif file_chunk := msg.get("file_chunk", None):
                filename = file_chunk.get("name", "")
                chunk_data = file_chunk.get("data", "")
                if filename in uploading_files:
                    state = uploading_files[filename]
                    try:
                        binary_data = base64.b64decode(chunk_data)
                        state["file_handle"].write(binary_data)
                        state["received"] += len(binary_data)
                    except Exception as e:
                        print(f"写入分片失败: {e}")

            elif msg.get("file_end", None):
                filename = msg.get("file_name", "")
                if filename in uploading_files:
                    state = uploading_files[filename]
                    state["file_handle"].close()
                    filepath = state["filepath"]
                    del uploading_files[filename]
                    print(f"文件接收完成: {filepath}")
                    try:
                        response = json.dumps(
                            {
                                "file_complete": True,
                                "name": os.path.basename(filepath),
                                "path": str(filepath),
                                "size": state["received"],
                            }
                        )
                        await websocket.send(response)
                    except Exception as e:
                        print(f"发送确认消息失败: {e}")

            elif coords := msg.get("three", None):
                if not alt:
                    pyautogui.keyDown("alt")
                    pyautogui.press("tab")
                    alt = True
                if abs(coords[0]) > 10:
                    pyautogui.press("right" if coords[0] > 0 else "left")
                if abs(coords[1]) > 10:
                    pyautogui.press("down" if coords[1] > 0 else "up")

            elif msg.get("threeEnd", None):
                if alt:
                    pyautogui.keyUp("alt")
                    alt = False
                    
    except websockets.exceptions.ConnectionClosed:
        print("\n====== 客户端断开连接 ======")
    except Exception as e:
        print(f"\n连接异常: {e}")
    finally:
        # 更新托盘图标为断开状态
        update_tray_icon(False)
        print("====== 连接已结束 ======")


# Flask路由
@app.route("/")
def index():
    """手机端触控板页面"""
    token = request.args.get("token")
    if token != WS_TOKEN:
        abort(403)
    return render_template("touchpad.html", ws_token=WS_TOKEN)


@app.route("/connect")
def connect_page():
    """电脑端连接页面"""
    return render_template("connect.html")


@app.route("/upload-dir", methods=["GET"])
def get_upload_dir():
    return jsonify({"path": str(UPLOAD_DIR_RESOLVED)})


@app.route("/upload-dir", methods=["POST"])
def update_upload_dir():
    data = request.get_json(silent=True) or {}
    target_path = str(data.get("path", "")).strip()
    if not target_path:
        return jsonify({"ok": False, "error": "目录不能为空"}), 400
    try:
        set_upload_dir(target_path)
        save_settings()
        return jsonify({"ok": True, "path": str(UPLOAD_DIR_RESOLVED)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/pick-upload-dir", methods=["POST"])
def pick_upload_dir():
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title="选择文件上传保存目录",
            initialdir=str(UPLOAD_DIR_RESOLVED),
            mustexist=False,
        )
        root.destroy()

        if not selected:
            return jsonify({"ok": False, "cancelled": True, "error": "已取消选择"}), 400

        set_upload_dir(selected)
        save_settings()
        return jsonify({"ok": True, "path": str(UPLOAD_DIR_RESOLVED)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/qrcode")
def get_qrcode():
    ip = socket.gethostbyname(socket.gethostname())
    url = f"http://{ip}:5000/?token={WS_TOKEN}"  # 手机扫码后进入触控板（根路径）

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    return jsonify({"qrcode": img_str, "ip": ip, "url": url})


def start_tray():
    """启动系统托盘"""
    print(f"[*] 启动系统托盘...", flush=True)
    try:
        # 直接调用create_tray_icon（它在独立线程中运行）
        create_tray_icon()
    except Exception as e:
        print(f"[!] 托盘启动失败: {e}", flush=True)
        import traceback
        traceback.print_exc()



def print_qrcode_ascii(ip):
    """在控制台打印ASCII二维码（开发模式）"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=2,
        )
        qr.add_data(f"http://{ip}:5000/")
        qr.make(fit=True)

        # 简单ASCII二维码
        from qrcode.console import make as qr_console

        print("\n" + "=" * 50)
        print("  手机扫码连接触控板")
        print("=" * 50)
        print(qr_console(qr, tunnel=None))
        print(f"或手动访问: http://{ip}:5000/")
        print("=" * 50 + "\n")
    except:
        print(f"\n手机扫码连接: http://{ip}:5000/\n")


async def main():
    load_settings()
    ip = socket.gethostbyname(socket.gethostname())
    port = 4000
    print(f"WebSocket服务器: ws://{ip}:{port}")
    print(f"HTTP服务器: http://{ip}:5000\n")

    # 启动系统托盘（后台线程，仅无控制台模式）
    tray_thread = threading.Thread(target=start_tray, daemon=True)
    tray_thread.start()

    # 启动Flask（后台线程）
    flask_thread = threading.Thread(
        target=lambda: app.run(host=ip, port=5000, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()

    await asyncio.sleep(1)

    # 判断是否为有控制台的模式
    has_console = (
        sys.stdout is not None
        and not sys.stdout.closed
        and hasattr(sys.stdout, "isatty")
        and sys.stdout.isatty()
    )

    if has_console:
        # 开发模式：控制台显示ASCII二维码
        print_qrcode_ascii(ip)

    # 两种模式都自动打开浏览器到连接页
    webbrowser.open(f"http://{ip}:5000/connect")

    # 启动WebSocket
    async with websockets.serve(handle_client, ip, port):
        # 使用英文避免编码问题
        status_msg = "Service running...\n    System tray icon shows status\n    Right-click tray icon to exit\n"
        print(status_msg)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
