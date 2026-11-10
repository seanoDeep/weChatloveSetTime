# -*- coding:utf-8 -*-
"""
统一配置管理 —— 供 UI 窗口、launcher、进程守护共同使用。

设计原则:
  1. 继续使用 config.ini 作为唯一真值来源，原有 [configuration] / [custom_tasks]
     结构完全不变，保证 say_to_lady.py 无需改动即可继续运行。
  2. 新增 [runtime] section 承载运行参数（应用路径 / 端口 / 运行模式 / 守护等）。
  3. save() 会保留必要的字段说明注释，未知的自定义字段原样保留。
"""
import configparser
import os
import re
import sys

SECTION_MAIN = 'configuration'
SECTION_TASKS = 'custom_tasks'
SECTION_RUNTIME = 'runtime'
SECTION_ORDER = [SECTION_MAIN, SECTION_TASKS, SECTION_RUNTIME]

ENCODING = 'UTF-8'

# HH:MM（00:00~23:59）或 99:99 表示不启用
TIME_RE = re.compile(r'^(([01]\d|2[0-3]):[0-5]\d|99:99)$')
TASK_KEY_RE = re.compile(r'^task(\d+)[._]([a-z]+)$')

VALID_MODES = {'custom', 'dict'}
VALID_DICT_KEYS = {'morning', 'lunch', 'dinner', 'dream', 'emoj', 'all'}
VALID_RUN_MODES = {'daemon', 'console'}

# (字段, 默认值, 注释)
_MAIN_FIELDS = [
    ('my_lady_wechat_name', '', '设置女友的微信名称，记住，不是微信ID也不是微信备注'),
    ('silent_mode', '0', '全局静默开关: 1=完全不输出任何控制台日志，0=正常输出'),
    ('birthday_month', '99', '女友生日月份(两位数)，99=不启用'),
    ('birthday_day', '99', '女友生日日期(两位数)，99=不启用'),
    ('say_good_morning', '99:99', '早上起床问候时间 HH:MM，99:99=不启用'),
    ('say_good_lunch', '99:99', '中午吃饭问候时间 HH:MM，99:99=不启用'),
    ('say_good_dinner', '99:99', '晚上吃饭问候时间 HH:MM，99:99=不启用'),
    ('say_good_dream', '99:99', '晚上睡觉问候时间 HH:MM，99:99=不启用'),
    ('flag_learn_english', '0', '睡觉问候是否附带每日学英语: 1=是，0=否'),
    ('flag_wx_emoj', '0', '所有问候语结尾是否加随机表情: 1=是，0=否'),
    ('str_Valentine', '亲爱的，情人节快乐！', '情人节祝福语'),
    ('str_Women', '嘿，女神节到了，祝我的女神开心快乐！', '三八妇女节祝福语'),
    ('str_Christmas_Eve', '宝贝，平安夜快乐！', '平安夜祝福语'),
    ('str_Christmas', '小仙女，圣诞节快乐哦！', '圣诞节祝福语'),
    ('str_birthday', '亲爱的，生日快乐！', '生日祝福语'),
]

_RUNTIME_FIELDS = [
    ('app_path', '', '要守护的应用路径；留空=使用内置 say_to_lady.py'),
    ('run_mode', 'daemon', '运行模式: daemon=后台守护 / console=前台控制台'),
    ('health_port', '0', '本地健康检查端口 0-65535，0=不启用'),
    ('keep_awake', '1', '后台保持活跃(阻止系统休眠): 1=开，0=关'),
    ('watchdog', '1', '进程守护(异常退出自动重启): 1=开，0=关'),
    ('watchdog_interval', '5', '守护轮询间隔(秒)，建议 2-30'),
    ('max_restarts_per_hour', '20', '每小时最大重启次数，超过后降速等待'),
    ('autostart', '0', '开机自启动: 1=开，0=关（保存配置时同步到系统）'),
]

_TASK_FIELDS = ['time', 'mode', 'content', 'dict', 'receiver']


class ConfigError(ValueError):
    """配置校验失败"""


def app_dir():
    """项目根目录：兼容源码运行与 PyInstaller 冻结后的运行"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def default_config_path():
    return os.path.join(app_dir(), 'config.ini')


def resource_dir():
    """打包后为 PyInstaller 的临时解包目录，源码运行为项目目录"""
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


def ensure_assets():
    """
    首次运行打包产物时，把内置的 config.ini 与句子库复制到 exe 同级目录，
    保证配置可写、用户可编辑；源码运行直接返回。
    """
    import shutil
    target = app_dir()
    source = resource_dir()
    if os.path.abspath(target) == os.path.abspath(source):
        return

    cfg_src = os.path.join(source, 'config.ini')
    cfg_dst = os.path.join(target, 'config.ini')
    if os.path.exists(cfg_src) and not os.path.exists(cfg_dst):
        try:
            shutil.copy2(cfg_src, cfg_dst)
        except OSError:
            pass

    dir_src = os.path.join(source, 'remind_sentence')
    dir_dst = os.path.join(target, 'remind_sentence')
    if os.path.isdir(dir_src) and not os.path.isdir(dir_dst):
        try:
            shutil.copytree(dir_src, dir_dst)
        except OSError:
            pass


class Config(object):
    def __init__(self, path=None):
        self.path = path or default_config_path()
        self.cf = configparser.ConfigParser(interpolation=None, strict=False)
        self.cf.optionxform = str.lower   # 与旧版行为一致
        self.load()

    # ---------------- 读写 ----------------
    def load(self):
        if os.path.exists(self.path):
            self.cf.read(self.path, encoding=ENCODING)
        self._ensure_defaults()
        return self

    def _ensure_defaults(self):
        for sec, fields in ((SECTION_MAIN, _MAIN_FIELDS),
                            (SECTION_RUNTIME, _RUNTIME_FIELDS)):
            if not self.cf.has_section(sec):
                self.cf.add_section(sec)
            for key, default, _comment in fields:
                if not self.cf.has_option(sec, key):
                    self.cf.set(sec, key, default)
        if not self.cf.has_section(SECTION_TASKS):
            self.cf.add_section(SECTION_TASKS)

    def get(self, key, section=SECTION_MAIN, fallback=''):
        if not self.cf.has_option(section, key):
            return fallback
        return self.cf.get(section, key, fallback=fallback)

    def get_int(self, key, section=SECTION_RUNTIME, fallback=0):
        try:
            return int(str(self.get(key, section, str(fallback))).strip())
        except (TypeError, ValueError):
            return fallback

    def get_bool(self, key, section=SECTION_RUNTIME, fallback=False):
        return str(self.get(key, section, '1' if fallback else '0')).strip() == '1'

    def set(self, key, value, section=SECTION_MAIN):
        if not self.cf.has_section(section):
            self.cf.add_section(section)
        self.cf.set(section, str(key), '' if value is None else str(value))

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, 'w', encoding=ENCODING, newline='\n') as f:
            f.write(self.render())

    def render(self):
        """生成带字段注释的配置文件文本"""
        out = [
            '# 微信守护女友配置文件',
            '# 推荐使用图形界面修改: python ui_config.py',
            '',
        ]
        for sec in SECTION_ORDER:
            if sec == SECTION_MAIN:
                out.extend(self._render_fields(sec, _MAIN_FIELDS))
            elif sec == SECTION_RUNTIME:
                out.extend([
                    '# ============================================================',
                    '# 运行参数（UI 配置窗口写入，也可手动修改）',
                    '# ============================================================',
                ])
                out.extend(self._render_fields(sec, _RUNTIME_FIELDS))
            else:
                out.extend(self._render_tasks())
        return '\n'.join(out).rstrip() + '\n'

    def _render_fields(self, sec, fields):
        lines = ['[%s]' % sec, '']
        known = set()
        for key, default, comment in fields:
            known.add(key.lower())
            lines.append('# ' + comment)
            lines.append('%s = %s' % (key, self.get(key, sec, default)))
            lines.append('')
        # 保留未知字段，避免用户手写的扩展项被覆盖
        for key in self.cf.options(sec):
            if key in known:
                continue
            lines.append('%s = %s' % (key, self.get(key, sec, '')))
        lines.append('')
        return lines

    def _render_tasks(self):
        lines = [
            '[%s]' % SECTION_TASKS,
            '',
            '# ============================================================',
            '# 自定义定时任务。每项包含:',
            '#   taskN_time     触发时间 HH:MM',
            '#   taskN_mode     custom(自定义内容) / dict(从默认字典随机)',
            '#   taskN_content  mode=custom 时必填',
            '#   taskN_dict     morning|lunch|dinner|dream|emoj|all',
            '#   taskN_receiver 接收人微信昵称，缺省=女友昵称',
            '# ============================================================',
            '',
        ]
        tasks = self.get_tasks()
        for i, t in enumerate(tasks, 1):
            lines.append('task%d_time = %s' % (i, t['time']))
            lines.append('task%d_mode = %s' % (i, t['mode']))
            if t['mode'] == 'custom':
                lines.append('task%d_content = %s' % (i, t['content']))
            else:
                lines.append('task%d_dict = %s' % (i, t['dict']))
            lines.append('task%d_receiver = %s' % (i, t['receiver']))
            lines.append('')
        # 保留未被识别的自定义字段
        for key in self.cf.options(SECTION_TASKS):
            if TASK_KEY_RE.match(key):
                continue
            lines.append('%s = %s' % (key, self.get(key, SECTION_TASKS, '')))
        lines.append('')
        return lines

    # ---------------- 自定义任务 ----------------
    def get_tasks(self):
        if not self.cf.has_section(SECTION_TASKS):
            return []
        items = dict(self.cf.items(SECTION_TASKS))
        buckets = {}
        for key, value in items.items():
            m = TASK_KEY_RE.match(key.lower())
            if not m:
                continue
            tid, field = int(m.group(1)), m.group(2)
            buckets.setdefault(tid, {})[field] = value

        tasks = []
        for tid in sorted(buckets):
            b = buckets[tid]
            tasks.append({
                'time': (b.get('time') or '').strip(),
                'mode': (b.get('mode') or 'custom').strip().lower(),
                'content': b.get('content', '') or '',
                'dict': (b.get('dict') or '').strip().lower(),
                'receiver': (b.get('receiver')
                             or self.get('my_lady_wechat_name')).strip(),
            })
        return tasks

    def set_tasks(self, tasks):
        for key in list(self.cf.options(SECTION_TASKS)):
            if TASK_KEY_RE.match(key):
                self.cf.remove_option(SECTION_TASKS, key)
        for i, t in enumerate(tasks, 1):
            self.set('task%d_time' % i, t.get('time', ''), SECTION_TASKS)
            self.set('task%d_mode' % i, t.get('mode', 'custom'), SECTION_TASKS)
            if t.get('mode') == 'dict':
                self.set('task%d_dict' % i, t.get('dict', 'all'), SECTION_TASKS)
            else:
                self.set('task%d_content' % i, t.get('content', ''), SECTION_TASKS)
            self.set('task%d_receiver' % i, t.get('receiver', ''), SECTION_TASKS)

    # ---------------- 校验 ----------------
    def validate(self):
        """返回错误信息列表；空列表表示通过"""
        errors = []
        name = self.get('my_lady_wechat_name').strip()
        if not name:
            errors.append('女友微信昵称不能为空')

        for key in ('say_good_morning', 'say_good_lunch',
                    'say_good_dinner', 'say_good_dream'):
            if not TIME_RE.match(self.get(key).strip()):
                errors.append('%s 时间格式错误（应为 HH:MM 或 99:99）' % key)

        if self.get('birthday_month').strip() not in (
                ['99'] + ['%02d' % i for i in range(1, 13)]):
            errors.append('生日月份应为 01-12 或 99')
        if self.get('birthday_day').strip() not in (
                ['99'] + ['%02d' % i for i in range(1, 32)]):
            errors.append('生日日期应为 01-31 或 99')

        for key in ('silent_mode', 'flag_learn_english', 'flag_wx_emoj'):
            if self.get(key).strip() not in ('0', '1'):
                errors.append('%s 只能为 0 或 1' % key)

        if self.get('run_mode', SECTION_RUNTIME).strip() not in VALID_RUN_MODES:
            errors.append('运行模式只能是 daemon 或 console')
        port = self.get_int('health_port', SECTION_RUNTIME, 0)
        if not 0 <= port <= 65535:
            errors.append('健康检查端口应在 0-65535 之间')
        for key in ('keep_awake', 'watchdog', 'autostart'):
            if self.get(key, SECTION_RUNTIME).strip() not in ('0', '1'):
                errors.append('%s 只能为 0 或 1' % key)
        if self.get_int('watchdog_interval', SECTION_RUNTIME, 5) < 1:
            errors.append('守护轮询间隔应 >= 1 秒')
        if self.get_int('max_restarts_per_hour', SECTION_RUNTIME, 20) < 1:
            errors.append('每小时最大重启次数应 >= 1')

        for idx, t in enumerate(self.get_tasks(), 1):
            if not TIME_RE.match(t['time']) or t['time'] == '99:99':
                errors.append('任务 %d 时间格式错误' % idx)
            if t['mode'] not in VALID_MODES:
                errors.append('任务 %d 模式只能是 custom 或 dict' % idx)
            if t['mode'] == 'custom' and not t['content'].strip():
                errors.append('任务 %d 为自定义模式，内容不能为空' % idx)
            if t['mode'] == 'dict' and t['dict'] not in VALID_DICT_KEYS:
                errors.append('任务 %d 字典来源无效' % idx)
        return errors


def load(path=None):
    return Config(path)


def platform_info():
    """跨设备兼容性信息（供 UI 状态栏与测试使用）"""
    import platform
    return {
        'os': sys.platform,
        'os_name': platform.system(),
        'arch': platform.machine(),
        'python': platform.python_version(),
        'frozen': bool(getattr(sys, 'frozen', False)),
        # Win32 键盘/剪贴板自动化仅 Windows 可用，其他平台会明确报错
        'automation_supported': sys.platform == 'win32',
    }
