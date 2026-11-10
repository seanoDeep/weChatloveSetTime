# -*- coding:utf-8 -*-
"""
统一启动入口 —— 供命令行 / 双击 / 开机自启动使用。

常用命令:
  python launcher.py ui                 打开图形配置窗口
  python launcher.py run                前台运行（便于看日志）
  python launcher.py daemon             前台运行守护模式（进程守护常驻）
  python launcher.py start              后台启动守护进程（静默，无窗口）
  python launcher.py stop               停止后台守护进程
  python launcher.py status             查看运行状态
  python launcher.py autostart on|off|status
  python launcher.py build              打包为 exe / app
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import config_manager as cm
import autostart
import supervisor as sp

BASE_DIR = cm.app_dir()
PID_FILE = os.path.join(BASE_DIR, 'run.pid')
CONFIG_PATH = cm.default_config_path()


def log(msg):
    print(msg, flush=True)


def load_cfg():
    return cm.Config(CONFIG_PATH)


# ---------------------------------------------------------------------------
# 子进程命令解析
# ---------------------------------------------------------------------------
def child_command(cfg=None):
    """要守护的业务进程命令"""
    cfg = cfg or load_cfg()
    app_path = cfg.get('app_path', cm.SECTION_RUNTIME).strip()
    if app_path:
        app_path = os.path.expanduser(os.path.expandvars(app_path))
        if app_path.lower().endswith('.py'):
            return [sys.executable, app_path]
        return [app_path]

    if getattr(sys, 'frozen', False):
        return [sys.executable, 'run']
    return [sys.executable, os.path.join(BASE_DIR, 'say_to_lady.py')]


def self_command(*args):
    if getattr(sys, 'frozen', False):
        return [sys.executable] + list(args)
    return [sys.executable, os.path.join(BASE_DIR, 'launcher.py')] + list(args)


# ---------------------------------------------------------------------------
# 本地健康检查服务
# ---------------------------------------------------------------------------
class HealthServer(object):
    def __init__(self, port, provider):
        self.port = int(port)
        self.provider = provider
        self._httpd = None
        self._thread = None

    def start(self):
        provider = self.provider

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path not in ('/', '/health'):
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(provider(), ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass   # 静默，不产生日志

        try:
            self._httpd = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
        except OSError as e:
            log('[健康检查] 端口 %d 不可用: %s' % (self.port, e))
            return False
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name='health', daemon=True)
        self._thread.start()
        return True

    def stop(self):
        if self._httpd:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------
def cmd_ui():
    from ui_config import run_ui
    run_ui(CONFIG_PATH)


def cmd_run():
    import say_to_lady
    say_to_lady.main()


def cmd_daemon():
    cfg = load_cfg()
    port = cfg.get_int('health_port', cm.SECTION_RUNTIME, 0)
    interval = cfg.get_int('watchdog_interval', cm.SECTION_RUNTIME, 5)
    max_restarts = cfg.get_int('max_restarts_per_hour', cm.SECTION_RUNTIME, 20)
    watch = cfg.get_bool('watchdog', cm.SECTION_RUNTIME, True)
    awake = cfg.get_bool('keep_awake', cm.SECTION_RUNTIME, True)
    silent = cfg.get_bool('silent_mode', cm.SECTION_MAIN, False)

    state = {'pid': os.getpid(), 'started_at': time.time()}
    sup_holder = {}

    def provider():
        sup = sup_holder.get('sup')
        data = {'status': 'running', 'pid': os.getpid(),
                'uptime': int(time.time() - state['started_at'])}
        if sup:
            data.update({'starts': sup.stats['starts'],
                         'restarts': sup.stats['restarts'],
                         'crashes': sup.stats['crashes'],
                         'child_alive': sup.running})
        return data

    health = HealthServer(port, provider) if port > 0 else None
    if health and health.start():
        state['health'] = 'http://127.0.0.1:%d/health' % port

    def on_event(level, message):
        if not silent:
            log('[%s] %s' % (level, message))

    cmd = child_command(cfg)
    sup = sp.Supervisor(
        cmd, cwd=BASE_DIR,
        check_interval=interval,
        restart_delay=max(1.0, interval),
        max_restarts_per_hour=max_restarts,
        keep_awake=awake,
        on_event=on_event,
    )
    sup_holder['sup'] = sup

    sp.write_pid(PID_FILE)
    try:
        if not silent:
            log('守护模式已启动，子进程: %s' % ' '.join(cmd))
            log('进程守护: %s | 保持活跃: %s | 健康端口: %s' % (
                '开' if watch else '关', '开' if awake else '关',
                port if port else '关'))
        if watch:
            sup.run()
        else:
            # 不守护：直接前台跑业务进程，等待其结束
            sup._spawn()
            while sup._proc and sup._proc.poll() is None:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sup.stop()
        sp.remove_pid(PID_FILE)
        if health:
            health.stop()


def cmd_start():
    pid = sp.read_pid(PID_FILE)
    if pid and sp.pid_alive(pid):
        log('已在运行中 (pid=%d)' % pid)
        return 0

    kwargs = dict(cwd=BASE_DIR)
    if sys.platform == 'win32':
        kwargs['creationflags'] = (getattr(subprocess, 'DETACHED_PROCESS', 0x8)
                                   | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x200))
    else:
        kwargs['start_new_session'] = True
    kwargs.update(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  stdin=subprocess.DEVNULL)

    args = ['daemon']
    if os.path.abspath(CONFIG_PATH) != os.path.abspath(cm.default_config_path()):
        args = ['--config', CONFIG_PATH, 'daemon']

    proc = subprocess.Popen(self_command(*args), **kwargs)
    # 等待守护进程写入 pid 文件
    for _ in range(50):
        time.sleep(0.1)
        pid = sp.read_pid(PID_FILE)
        if pid and sp.pid_alive(pid):
            log('后台守护进程已启动 (pid=%d)' % pid)
            return 0
    log('启动超时，请检查配置或使用 python launcher.py daemon 前台排查')
    return 1


def cmd_stop():
    pid = sp.read_pid(PID_FILE)
    if not pid:
        log('未发现运行中的守护进程')
        return 0
    if not sp.pid_alive(pid):
        sp.remove_pid(PID_FILE)
        log('守护进程已不在运行，已清理 pid 文件')
        return 0

    try:
        if sys.platform == 'win32':
            subprocess.call(['taskkill', '/PID', str(pid), '/T', '/F'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, 15)
    except Exception as e:
        log('停止失败: %s' % e)
        return 1

    for _ in range(30):
        time.sleep(0.1)
        if not sp.pid_alive(pid):
            break
    sp.remove_pid(PID_FILE)
    log('已停止守护进程 (pid=%d)' % pid)
    return 0


def cmd_status():
    cfg = load_cfg()
    pid = sp.read_pid(PID_FILE)
    alive = sp.pid_alive(pid)

    info = {
        '进程状态': '运行中' if alive else '未运行',
        'PID': pid if pid else '-',
        '运行模式': cfg.get('run_mode', cm.SECTION_RUNTIME, 'daemon'),
        '进程守护': '开' if cfg.get_bool('watchdog', cm.SECTION_RUNTIME, True) else '关',
        '保持活跃': '开' if cfg.get_bool('keep_awake', cm.SECTION_RUNTIME, True) else '关',
        '静默模式': '开' if cfg.get_bool('silent_mode', cm.SECTION_MAIN, False) else '关',
        '开机自启': '开' if autostart.is_enabled() else '关',
        '健康端口': cfg.get('health_port', cm.SECTION_RUNTIME, '0'),
        '女友昵称': cfg.get('my_lady_wechat_name'),
        '自定义任务': '%d 个' % len(cfg.get_tasks()),
        '平台': '%s / %s' % (sys.platform, sys.version.split()[0]),
    }

    port = cfg.get_int('health_port', cm.SECTION_RUNTIME, 0)
    if port > 0:
        try:
            with urlopen('http://127.0.0.1:%d/health' % port, timeout=2) as r:
                info['健康检查'] = json.loads(r.read().decode('utf-8')).get('status', '?')
        except Exception:
            info['健康检查'] = '不可达'

    log('=' * 46)
    for k, v in info.items():
        log('  %-8s : %s' % (k, v))
    log('=' * 46)
    return 0 if alive else 3


def cmd_autostart(action):
    if action == 'status':
        enabled, detail = autostart.status()
        log('开机自启: %s' % ('已启用' if enabled else '未启用'))
        if detail:
            log('  详情: %s' % detail)
        return 0
    if action == 'on':
        log(autostart.enable())
        return 0
    if action == 'off':
        log(autostart.disable())
        return 0
    log('用法: launcher.py autostart on|off|status')
    return 2


def cmd_build(argv):
    import build
    return build.main(argv)


# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(description='微信守护女友 - 统一启动入口')
    p.add_argument('--config', default=CONFIG_PATH, help='配置文件路径')
    sub = p.add_subparsers(dest='command')

    sub.add_parser('ui', help='打开图形配置窗口')
    sub.add_parser('run', help='前台运行（不守护）')
    sub.add_parser('daemon', help='前台运行守护模式')
    sub.add_parser('start', help='后台启动守护进程')
    sub.add_parser('stop', help='停止后台守护进程')
    sub.add_parser('status', help='查看运行状态')
    asub = sub.add_parser('autostart', help='开机自启动管理')
    asub.add_argument('action', choices=['on', 'off', 'status'])
    return p


def main(argv=None):
    global CONFIG_PATH
    argv = list(sys.argv[1:] if argv is None else argv)

    # build 子命令透传给 build.py
    if argv and argv[0] == 'build':
        return cmd_build(argv[1:])

    parser = build_parser()
    args = parser.parse_args(argv)
    CONFIG_PATH = args.config
    cm.ensure_assets()   # 打包后首次运行：复制内置配置与句子库到 exe 同级

    cmd = args.command or 'ui'
    if cmd == 'ui':
        cmd_ui()
        return 0
    if cmd == 'run':
        cmd_run()
        return 0
    if cmd == 'daemon':
        cmd_daemon()
        return 0
    if cmd == 'start':
        return cmd_start()
    if cmd == 'stop':
        return cmd_stop()
    if cmd == 'status':
        return cmd_status()
    if cmd == 'autostart':
        return cmd_autostart(args.action)
    parser.print_help()
    return 2


if __name__ == '__main__':
    sys.exit(main())
