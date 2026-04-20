"""
打包脚本 - 无线触控板
仅生成窗口版本（发布用）
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.absolute()
APP_DIR = PROJECT_ROOT / "app"
SERVER_DIR = PROJECT_ROOT / "server"


def clean_build_dirs():
    """清理构建目录"""
    print("[*] 清理构建目录...")
    dirs_to_clean = [
        PROJECT_ROOT / "build",
        PROJECT_ROOT / "dist",
        PROJECT_ROOT / "__pycache__",
        APP_DIR / "__pycache__",
        SERVER_DIR / "__pycache__",
    ]
    for d in dirs_to_clean:
        if d.exists():
            shutil.rmtree(d)
            print(f"   已删除: {d}")


def install_dependencies():
    """安装依赖（使用uv）"""
    print("[*] 检查依赖...")
    requirements_file = PROJECT_ROOT / "requirements.txt"
    # 使用uv同步安装
    result = subprocess.run(
        ["uv", "pip", "install", "-r", str(requirements_file)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"[!] 依赖安装可能有问题: {result.stderr}")
    else:
        print("   依赖安装完成")


def build_windowed_version():
    """构建窗口版本（发布用）"""
    print("\n[*] 构建窗口版本...")

    cmd = [
        "pyinstaller",
        "--name=无线触控板",
        "--onefile",
        "--windowed",
        "--add-data",
        "server/templates;server/templates",
        "--hidden-import",
        "win32gui",
        "--hidden-import",
        "win32con",
        "--hidden-import",
        "win32api",
        "--hidden-import",
        "pystray",
        "--hidden-import",
        "PIL._tkinter_finder",  # PIL依赖
        "--clean",
        "--noconfirm",
        str(APP_DIR / "main.py"),
    ]

    icon_path = PROJECT_ROOT / "icon.ico"
    if icon_path.exists():
        cmd.insert(2, f"--icon={icon_path}")

    subprocess.check_call(cmd, cwd=PROJECT_ROOT)
    print("   [OK] 窗口版本构建完成: dist/无线触控板.exe")


def main():
    print("=" * 60)
    print("无线触控板 - 打包工具")
    print("=" * 60)

    # 检查pyinstaller是否安装
    try:
        import PyInstaller
    except ImportError:
        print("[!] 未安装PyInstaller，正在安装...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("   PyInstaller安装完成")

    # 安装依赖
    install_dependencies()

    # 清理
    clean_build_dirs()

    # 仅构建窗口版本
    build_windowed_version()

    print("\n" + "=" * 60)
    print("[OK] 打包完成！")
    print("=" * 60)
    print("\n生成的文件:")
    print(f"  窗口版: {PROJECT_ROOT}/dist/无线触控板.exe")
    print("\n使用说明:")
    print("  双击运行，无控制台窗口，自动打开浏览器显示二维码")
    print("=" * 60)


if __name__ == "__main__":
    main()
