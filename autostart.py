# -*- coding:utf-8 -*-
"""
开机自启动管理（跨平台）:
  Windows : HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
  macOS   : ~/Library/LaunchAgents/com.saytolady.agent.plist
  Linux   : ~/.config/autostart/say-to-lady.desktop

DRY_RUN=True 时只计算不写入，便于测试。
"""
import os
import sys

DRY_RUN = False

APP_NAME = 'SayToLady'
WIN_RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
MAC_PLIST_NAME = 'com.saytolady.agent.plist'


def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def default_command():
    """
    生成“以守护模式启动”的自启动命令。
    冻结后:   SayToLady.exe daemon
    源码运行: python launcher.py daemon
    """
    if getattr(sys, 'frozen', False):
        exe = os.path.abspath(sys.executable)
        return '"%s" daemon' % exe
    py = os.path.abspath(sys.executable)
    launcher = os.path.join(app_dir(), 'launcher.py')
    return '"%s" "%s" daemon' % (py, launcher)


def status():
    """返回 (enabled: bool, detail: str)"""
    if sys.platform == 'win32':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, APP_NAME)
                return True, value
        except FileNotFoundError:
            return False, ''
        except OSError as e:
            return False, '读取注册表失败: %s' % e
    if sys.platform == 'darwin':
        path = _mac_plist_path()
        return os.path.exists(path), path
    path = _linux_desktop_path()
    return os.path.exists(path), path


def is_enabled():
    return status()[0]


def enable(command=None):
    """写入自启动项，返回说明文字"""
    command = command or default_command()
    if DRY_RUN:
        return '[dry-run] 将写入自启动项: %s' % command

    if sys.platform == 'win32':
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        return '已写入注册表 Run 项: %s' % command

    if sys.platform == 'darwin':
        path = _mac_plist_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        plist = _mac_plist_content(command)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(plist)
        return '已创建 LaunchAgent: %s' % path

    path = _linux_desktop_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(_linux_desktop_content(command))
    return '已创建 autostart 项: %s' % path


def disable():
    """移除自启动项，返回说明文字"""
    if DRY_RUN:
        return '[dry-run] 将删除自启动项'

    if sys.platform == 'win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, APP_NAME)
            return '已从注册表 Run 项移除'
        except FileNotFoundError:
            return '自启动项本就不存在'
        except OSError as e:
            return '移除失败: %s' % e

    path = _mac_plist_path() if sys.platform == 'darwin' else _linux_desktop_path()
    if os.path.exists(path):
        os.remove(path)
        return '已删除: %s' % path
    return '自启动项本就不存在'


def sync(enabled):
    """按期望状态同步（UI 保存时调用）"""
    current = is_enabled()
    if enabled and not current:
        return enable()
    if not enabled and current:
        return disable()
    return '状态一致，无需变更'


# ---------------- 平台细节 ----------------
def _mac_plist_path():
    return os.path.expanduser(
        '~/Library/LaunchAgents/' + MAC_PLIST_NAME)


def _mac_plist_content(command):
    parts = _split_command(command)
    args = ''.join('        <string>%s</string>\n' % a for a in parts)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        '<dict>\n'
        '    <key>Label</key>\n'
        '    <string>%s</string>\n'
        '    <key>ProgramArguments</key>\n'
        '    <array>\n%s    </array>\n'
        '    <key>RunAtLoad</key>\n'
        '    <true/>\n'
        '    <key>KeepAlive</key>\n'
        '    <true/>\n'
        '</dict>\n'
        '</plist>\n' % (APP_NAME, args)
    )


def _linux_desktop_path():
    return os.path.expanduser('~/.config/autostart/say-to-lady.desktop')


def _linux_desktop_content(command):
    return (
        '[Desktop Entry]\n'
        'Type=Application\n'
        'Name=Say To Lady\n'
        'Exec=%s\n'
        'X-GNOME-Autostart-enabled=true\n'
        'Terminal=false\n' % command
    )


def _split_command(command):
    """把 '"C:\\a b\\x.exe" daemon' 拆成 ['C:\\a b\\x.exe', 'daemon']"""
    import shlex
    try:
        return shlex.split(command, posix=sys.platform != 'win32')
    except ValueError:
        return [command]


if __name__ == '__main__':
    print('平台:', sys.platform)
    print('当前状态:', status())
    print('默认命令:', default_command())
