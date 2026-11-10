# -*- coding:utf-8 -*-
"""
进程守护 + 后台保活

Supervisor:
  - 启动子进程并轮询其状态
  - 子进程异常退出（崩溃 / 被任务管理器结束）后自动重启
  - 指数退避 + 每小时重启次数上限，避免疯狂重启拖垮机器

KeepAwake:
  - Windows: SetThreadExecutionState 阻止系统休眠 / 锁屏回收
  - 其他平台: 空实现（系统本身不会因空闲杀掉普通进程）
"""
import collections
import ctypes
import os
import subprocess
import sys
import threading
import time


# ---------------------------------------------------------------------------
# 后台保活
# ---------------------------------------------------------------------------
class KeepAwake(object):
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    def __init__(self, enabled=True):
        self.enabled = enabled and sys.platform == 'win32'
        self._acquired = False

    def acquire(self):
        if not self.enabled or self._acquired:
            return False
        try:
            # 只请求系统保持唤醒，不强制点亮屏幕
            ctypes.windll.kernel32.SetThreadExecutionState(
                self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED)
            self._acquired = True
            return True
        except Exception:
            self.enabled = False
            return False

    def release(self):
        if not self._acquired:
            return
        try:
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
        except Exception:
            pass
        self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


# ---------------------------------------------------------------------------
# 进程守护
# ---------------------------------------------------------------------------
class Supervisor(object):
    def __init__(self, command, cwd=None, check_interval=5.0,
                 restart_delay=2.0, max_delay=60.0,
                 max_restarts_per_hour=20, keep_awake=False,
                 on_event=None, health_probe=None):
        """
        command            : list，要守护的命令
        check_interval     : 子进程存活轮询间隔（秒）
        restart_delay      : 首次重启等待（秒），之后指数退避
        max_restarts_per_hour: 每小时重启上限
        keep_awake         : 是否阻止系统休眠
        on_event           : 事件回调 fn(level, message)
        health_probe       : 可选 fn() -> bool，返回 False 视为假死并重启
        """
        self.command = list(command)
        self.cwd = cwd or os.getcwd()
        self.check_interval = max(0.05, float(check_interval))
        self.restart_delay = max(0.01, float(restart_delay))
        self.max_delay = max_delay
        self.max_restarts_per_hour = max(1, int(max_restarts_per_hour))
        self.keep_awake = bool(keep_awake)
        self.on_event = on_event
        self.health_probe = health_probe

        self._stop = threading.Event()
        self._proc = None
        self._restart_times = collections.deque()
        self.stats = {
            'starts': 0,
            'restarts': 0,
            'crashes': 0,
            'last_exit_code': None,
            'last_start': None,
            'started_at': None,
        }

    # ---------- 对外 ----------
    def run(self):
        """阻塞运行，直到 stop() 被调用"""
        self.stats['started_at'] = time.time()
        awake = KeepAwake(self.keep_awake)
        if self.keep_awake:
            awake.acquire()
        consecutive = 0
        try:
            while not self._stop.is_set():
                self._spawn()
                if not self._wait_child_exit():
                    break                      # 被 stop 打断

                code = self._proc.returncode if self._proc else None
                self.stats['last_exit_code'] = code
                self.stats['crashes'] += 1
                self._emit('warn', '子进程退出 (code=%s)，准备重启' % code)

                uptime = time.time() - (self.stats['last_start'] or time.time())
                consecutive = 1 if uptime > 60 else consecutive + 1

                delay = self._backoff(consecutive)
                if self._stop.wait(delay):
                    break
        finally:
            self._terminate_child()
            awake.release()
            self.stats['stopped_at'] = time.time()

    def stop(self):
        self._stop.set()
        self._terminate_child()

    @property
    def running(self):
        return self._proc is not None and self._proc.poll() is None

    # ---------- 内部 ----------
    def _spawn(self):
        kwargs = dict(cwd=self.cwd, stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        if sys.platform == 'win32':
            # 不弹出控制台窗口
            kwargs['creationflags'] = getattr(
                subprocess, 'CREATE_NO_WINDOW', 0x08000000)
        try:
            self._proc = subprocess.Popen(self.command, **kwargs)
        except Exception as e:
            self._proc = None
            self._emit('error', '启动子进程失败: %s' % e)
            return
        self.stats['starts'] += 1
        self.stats['last_start'] = time.time()
        self._emit('info', '子进程已启动 pid=%s' % self._proc.pid)

    def _wait_child_exit(self):
        """返回 True=子进程已退出（需要重启）；False=被 stop 打断"""
        while not self._stop.is_set():
            if self._proc is None:
                return True
            if self._proc.poll() is not None:
                return True
            if self.health_probe is not None:
                try:
                    if not self.health_probe():
                        self._emit('warn', '健康检查失败，判定为假死并重启')
                        self._terminate_child()
                        return True
                except Exception:
                    pass
            self._stop.wait(self.check_interval)
        return False

    def _backoff(self, consecutive):
        now = time.time()
        while self._restart_times and now - self._restart_times[0] > 3600:
            self._restart_times.popleft()

        if len(self._restart_times) >= self.max_restarts_per_hour:
            self._emit('error',
                       '一小时重启次数已达上限(%d)，等待 5 分钟'
                       % self.max_restarts_per_hour)
            return 300.0

        self._restart_times.append(now)
        self.stats['restarts'] += 1
        delay = min(self.max_delay, self.restart_delay * (2 ** min(consecutive - 1, 5)))
        self._emit('info', '%.1f 秒后重启 (第 %d 次)'
                   % (delay, self.stats['restarts']))
        return delay

    def _terminate_child(self):
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
        finally:
            self._proc = None

    def _emit(self, level, message):
        if self.on_event:
            try:
                self.on_event(level, message)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# PID 文件工具
# ---------------------------------------------------------------------------
def write_pid(path, pid=None):
    pid = pid or os.getpid()
    with open(path, 'w', encoding='utf-8') as f:
        f.write(str(pid))
    return pid


def read_pid(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def remove_pid(path):
    try:
        os.remove(path)
    except OSError:
        pass


def pid_alive(pid):
    if not pid:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
    except Exception:
        if sys.platform == 'win32':
            # 无 psutil 时用 tasklist 兜底
            try:
                out = subprocess.check_output(
                    ['tasklist', '/FI', 'PID eq %d' % pid],
                    stderr=subprocess.DEVNULL).decode('mbcs', 'ignore')
                return str(pid) in out
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
