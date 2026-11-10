# -*- coding:utf-8 -*-
"""
打包脚本 —— 用 PyInstaller 生成轻量化产物

用法:
  python build.py                # 单文件打包（两个目标）
  python build.py --onedir       # 目录模式，启动更快
  python build.py --console      # 保留控制台，便于排查
  python build.py --clean        # 打包前清空 build/dist

产物:
  dist/SayToLady(.exe)         业务入口：ui / run / daemon / start / stop / status
  dist/SayToLadyConfig(.exe)   直接打开可视化配置窗口

跨平台:
  Windows 产物仅能在 Windows 运行；macOS 需在 macOS 上执行本脚本生成 .app；
  微信自动发送依赖 Win32，仅 Windows 可用（其他平台可使用配置/守护能力）。
"""
import argparse
import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 明显用不到的重型依赖，排除后体积更小
EXCLUDES = [
    'numpy', 'pandas', 'matplotlib', 'scipy', 'PIL', 'PyQt5', 'PySide2',
    'PySide6', 'IPython', 'pytest', 'notebook', 'jupyter', 'sqlalchemy',
    'setuptools', 'pip', 'wheel',
]

TARGETS = [
    {
        'name': 'SayToLady',
        'entry': 'launcher.py',
        'excludes': EXCLUDES + ['tkinter'],
        'description': '统一入口',
    },
    {
        'name': 'SayToLadyConfig',
        'entry': 'ui_config.py',
        'excludes': EXCLUDES,
        'description': '配置窗口',
    },
]


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        print('未检测到 PyInstaller，请先安装:')
        print('  python -m pip install pyinstaller')
        return False


def separator():
    return ';' if sys.platform == 'win32' else ':'


def build_target(target, onefile=True, console=False, clean=False):
    sep = separator()
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--name', target['name'],
        '--distpath', os.path.join(BASE_DIR, 'dist'),
        '--workpath', os.path.join(BASE_DIR, 'build'),
        '--specpath', os.path.join(BASE_DIR, 'build'),
        '--onefile' if onefile else '--onedir',
        '--console' if console else '--windowed',
        '--add-data', os.path.join(BASE_DIR, 'config.ini') + sep + '.',
        '--add-data', (os.path.join(BASE_DIR, 'remind_sentence')
                       + sep + 'remind_sentence'),
    ]
    if clean:
        cmd.append('--clean')
    for mod in target['excludes']:
        cmd.extend(['--exclude-module', mod])
    cmd.append(os.path.join(BASE_DIR, target['entry']))

    print('\n>>> 打包 %s (%s)' % (target['name'], target['description']))
    print('    ' + ' '.join(cmd))
    return subprocess.call(cmd, cwd=BASE_DIR)


def clean_outputs():
    for name in ('build', 'dist'):
        path = os.path.join(BASE_DIR, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            print('已清理:', path)


def main(argv=None):
    parser = argparse.ArgumentParser(description='打包微信守护女友')
    parser.add_argument('--onedir', action='store_true', help='目录模式（默认单文件）')
    parser.add_argument('--console', action='store_true', help='保留控制台窗口')
    parser.add_argument('--clean', action='store_true', help='打包前清理 build/dist')
    parser.add_argument('--target', choices=[t['name'] for t in TARGETS],
                        help='只打指定目标')
    args = parser.parse_args(argv)

    if not ensure_pyinstaller():
        return 1

    if args.clean:
        clean_outputs()

    targets = [t for t in TARGETS
               if not args.target or t['name'] == args.target]

    failed = 0
    for t in targets:
        rc = build_target(t, onefile=not args.onedir,
                          console=args.console, clean=False)
        if rc != 0:
            failed += 1
            print('打包失败:', t['name'])

    if failed:
        return 1

    print('\n全部完成，产物位于:', os.path.join(BASE_DIR, 'dist'))
    print('提示: 首次运行会自动在产物同级目录生成 config.ini 与 remind_sentence/')
    return 0


if __name__ == '__main__':
    sys.exit(main())
