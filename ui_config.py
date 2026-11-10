# -*- coding:utf-8 -*-
"""
可视化配置窗口（tkinter，跨平台）

启动方式:
  python ui_config.py
  python launcher.py ui

三个页签:
  1. 基础设置 —— 昵称 / 四个问候时间 / 生日 / 开关
  2. 自定义任务 —— 任意多组定时发送（自定义内容或默认字典随机）
  3. 运行与系统 —— 应用路径 / 端口 / 运行模式 / 守护 / 开机自启
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import config_manager as cm
import autostart
import supervisor as sp

DICT_CHOICES = ['morning', 'lunch', 'dinner', 'dream', 'emoj', 'all']
MODE_LABELS = {'custom': '自定义内容', 'dict': '默认字典随机'}
MODE_VALUES = ['custom', 'dict']


class ConfigWindow(tk.Tk):
    def __init__(self, config_path=None):
        super().__init__()
        self.cfg = cm.Config(config_path)
        self.tasks = self.cfg.get_tasks()

        self.title('微信守护女友 · 配置中心')
        self.geometry('820x660')
        self.minsize(760, 600)
        try:
            self.tk.call('tk', 'scaling', 1.2)
        except Exception:
            pass

        self._v = {}
        self._build()
        self._load_into_ui()
        self._refresh_task_tree()
        self._refresh_status()

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------
    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=10, pady=(10, 4))

        self._tab_basic(nb)
        self._tab_tasks(nb)
        self._tab_runtime(nb)

        bar = ttk.Frame(self)
        bar.pack(fill='x', padx=10, pady=(0, 4))
        self.status_var = tk.StringVar(value='就绪')
        ttk.Label(bar, textvariable=self.status_var,
                  foreground='#555').pack(side='left')

        btns = ttk.Frame(self)
        btns.pack(fill='x', padx=10, pady=(0, 10))
        ttk.Button(btns, text='保存配置', command=self.on_save).pack(side='left')
        ttk.Button(btns, text='后台启动', command=self.on_start).pack(side='left', padx=6)
        ttk.Button(btns, text='停止后台', command=self.on_stop).pack(side='left')
        ttk.Button(btns, text='刷新状态', command=self._refresh_status).pack(side='left', padx=6)
        ttk.Button(btns, text='关闭', command=self.destroy).pack(side='right')

    # ---------------- 页签 1 ----------------
    def _tab_basic(self, nb):
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text='基础设置')

        def row(r, label, widget, hint=''):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky='w', pady=4)
            widget.grid(row=r, column=1, sticky='w', pady=4)
            if hint:
                ttk.Label(f, text=hint, foreground='#888').grid(
                    row=r, column=2, sticky='w', padx=8)

        self._v['my_lady_wechat_name'] = tk.StringVar()
        row(0, '女友微信昵称', ttk.Entry(f, textvariable=self._v['my_lady_wechat_name'], width=28),
            '微信中显示的昵称，不是微信号')

        ttk.Separator(f, orient='horizontal').grid(
            row=1, column=0, columnspan=3, sticky='ew', pady=8)

        for i, (key, label) in enumerate([
                ('say_good_morning', '早上起床时间'),
                ('say_good_lunch', '中午吃饭时间'),
                ('say_good_dinner', '晚上吃饭时间'),
                ('say_good_dream', '晚上睡觉时间')]):
            self._v[key] = tk.StringVar()
            row(i + 2, label, ttk.Entry(f, textvariable=self._v[key], width=12),
                'HH:MM（24 小时制，补零），99:99 = 不启用')

        ttk.Separator(f, orient='horizontal').grid(
            row=6, column=0, columnspan=3, sticky='ew', pady=8)

        self._v['birthday_month'] = tk.StringVar()
        self._v['birthday_day'] = tk.StringVar()
        bf = ttk.Frame(f)
        bf.grid(row=7, column=1, sticky='w')
        ttk.Entry(bf, textvariable=self._v['birthday_month'], width=5).pack(side='left')
        ttk.Label(bf, text=' 月 ').pack(side='left')
        ttk.Entry(bf, textvariable=self._v['birthday_day'], width=5).pack(side='left')
        ttk.Label(bf, text=' 日').pack(side='left')
        ttk.Label(f, text='生日').grid(row=7, column=0, sticky='w')
        ttk.Label(f, text='99 = 不启用', foreground='#888').grid(
            row=7, column=2, sticky='w', padx=8)

        self._v['silent_mode'] = tk.BooleanVar()
        self._v['flag_learn_english'] = tk.BooleanVar()
        self._v['flag_wx_emoj'] = tk.BooleanVar()
        opts = ttk.Frame(f)
        opts.grid(row=8, column=0, columnspan=3, sticky='w', pady=(10, 0))
        ttk.Checkbutton(opts, text='静默模式（完全不输出控制台日志）',
                        variable=self._v['silent_mode']).pack(anchor='w')
        ttk.Checkbutton(opts, text='睡觉问候附带每日学英语',
                        variable=self._v['flag_learn_english']).pack(anchor='w')
        ttk.Checkbutton(opts, text='问候语结尾加随机表情',
                        variable=self._v['flag_wx_emoj']).pack(anchor='w')

    # ---------------- 页签 2 ----------------
    def _tab_tasks(self, nb):
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text='自定义任务')

        cols = ('time', 'mode', 'content', 'receiver')
        self.tree = ttk.Treeview(f, columns=cols, show='headings', height=9)
        for c, t, w in (('time', '时间', 80), ('mode', '模式', 110),
                        ('content', '内容 / 字典来源', 320), ('receiver', '接收人', 140)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor='w')
        self.tree.grid(row=0, column=0, columnspan=4, sticky='nsew')
        self.tree.bind('<<TreeviewSelect>>', self._on_task_select)

        editor = ttk.LabelFrame(f, text='编辑任务', padding=10)
        editor.grid(row=1, column=0, columnspan=4, sticky='ew', pady=10)

        self._v['t_time'] = tk.StringVar(value='10:00')
        self._v['t_mode'] = tk.StringVar(value='custom')
        self._v['t_content'] = tk.StringVar()
        self._v['t_dict'] = tk.StringVar(value='all')
        self._v['t_receiver'] = tk.StringVar()

        ttk.Label(editor, text='时间').grid(row=0, column=0, sticky='w')
        ttk.Entry(editor, textvariable=self._v['t_time'], width=10).grid(
            row=0, column=1, sticky='w', padx=(4, 12))
        ttk.Label(editor, text='模式').grid(row=0, column=2, sticky='w')
        mode_cb = ttk.Combobox(editor, textvariable=self._v['t_mode'],
                               values=MODE_VALUES, width=12, state='readonly')
        mode_cb.grid(row=0, column=3, sticky='w', padx=(4, 12))
        mode_cb.bind('<<ComboboxSelected>>', lambda e: self._sync_editor_state())

        ttk.Label(editor, text='内容').grid(row=1, column=0, sticky='w', pady=6)
        self.ent_content = ttk.Entry(editor, textvariable=self._v['t_content'], width=46)
        self.ent_content.grid(row=1, column=1, columnspan=3, sticky='w', padx=(4, 0), pady=6)

        ttk.Label(editor, text='字典').grid(row=2, column=0, sticky='w')
        self.cb_dict = ttk.Combobox(editor, textvariable=self._v['t_dict'],
                                    values=DICT_CHOICES, width=12,
                                    state='readonly')
        self.cb_dict.grid(row=2, column=1, sticky='w', padx=(4, 12))

        ttk.Label(editor, text='接收人').grid(row=2, column=2, sticky='w')
        ttk.Entry(editor, textvariable=self._v['t_receiver'], width=18).grid(
            row=2, column=3, sticky='w', padx=(4, 0))

        btns = ttk.Frame(f)
        btns.grid(row=2, column=0, columnspan=4, sticky='w')
        ttk.Button(btns, text='添加任务', command=self.on_task_add).pack(side='left')
        ttk.Button(btns, text='更新选中', command=self.on_task_update).pack(side='left', padx=6)
        ttk.Button(btns, text='删除选中', command=self.on_task_delete).pack(side='left')
        ttk.Label(btns, text='  接收人留空则默认为女友昵称',
                  foreground='#888').pack(side='left', padx=10)

        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

    # ---------------- 页签 3 ----------------
    def _tab_runtime(self, nb):
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text='运行与系统')

        def row(r, label, widget, hint=''):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky='w', pady=5)
            widget.grid(row=r, column=1, sticky='w', pady=5)
            if hint:
                ttk.Label(f, text=hint, foreground='#888').grid(
                    row=r, column=2, sticky='w', padx=8)

        self._v['app_path'] = tk.StringVar()
        ap = ttk.Frame(f)
        ap.grid(row=0, column=1, sticky='w')
        ttk.Entry(ap, textvariable=self._v['app_path'], width=44).pack(side='left')
        ttk.Button(ap, text='浏览…', width=8,
                   command=self._pick_app).pack(side='left', padx=4)
        ttk.Label(f, text='应用路径').grid(row=0, column=0, sticky='w')
        ttk.Label(f, text='留空 = 使用内置 say_to_lady.py', foreground='#888').grid(
            row=0, column=2, sticky='w', padx=8)

        self._v['run_mode'] = tk.StringVar(value='daemon')
        row(1, '运行模式', ttk.Combobox(f, textvariable=self._v['run_mode'],
                                    values=['daemon', 'console'], width=12,
                                    state='readonly'), 'daemon=后台静默 / console=前台')

        self._v['health_port'] = tk.StringVar(value='0')
        row(2, '健康检查端口', ttk.Entry(f, textvariable=self._v['health_port'], width=12),
            '0 = 不启用；建议 8000-8999')

        self._v['keep_awake'] = tk.BooleanVar(value=True)
        self._v['watchdog'] = tk.BooleanVar(value=True)
        self._v['autostart'] = tk.BooleanVar()
        opt = ttk.Frame(f)
        opt.grid(row=3, column=0, columnspan=3, sticky='w', pady=(10, 0))
        ttk.Checkbutton(opt, text='后台保持活跃（阻止系统休眠回收）',
                        variable=self._v['keep_awake']).pack(anchor='w')
        ttk.Checkbutton(opt, text='进程守护（异常退出 / 被关闭后自动重启）',
                        variable=self._v['watchdog']).pack(anchor='w')
        ttk.Checkbutton(opt, text='开机自启动（保存时同步到系统）',
                        variable=self._v['autostart']).pack(anchor='w')

        self._v['watchdog_interval'] = tk.StringVar(value='5')
        row(4, '守护轮询间隔(秒)',
            ttk.Entry(f, textvariable=self._v['watchdog_interval'], width=12),
            '2-30 之间较合适')

        self._v['max_restarts_per_hour'] = tk.StringVar(value='20')
        row(5, '每小时最大重启',
            ttk.Entry(f, textvariable=self._v['max_restarts_per_hour'], width=12),
            '超过后降速等待，防止疯狂重启')

        ttk.Separator(f, orient='horizontal').grid(
            row=6, column=0, columnspan=3, sticky='ew', pady=10)
        ttk.Label(f, text='系统信息', foreground='#555').grid(
            row=7, column=0, columnspan=3, sticky='w')
        self.runtime_info = tk.StringVar()
        ttk.Label(f, textvariable=self.runtime_info, justify='left',
                  foreground='#333').grid(row=8, column=0, columnspan=3, sticky='w')

    # ------------------------------------------------------------------
    # 数据装载 / 保存
    # ------------------------------------------------------------------
    def _load_into_ui(self):
        c = self.cfg
        for key in ('my_lady_wechat_name', 'say_good_morning', 'say_good_lunch',
                    'say_good_dinner', 'say_good_dream', 'birthday_month',
                    'birthday_day'):
            self._v[key].set(c.get(key))

        self._v['silent_mode'].set(c.get_bool('silent_mode', cm.SECTION_MAIN, False))
        self._v['flag_learn_english'].set(
            c.get_bool('flag_learn_english', cm.SECTION_MAIN, False))
        self._v['flag_wx_emoj'].set(
            c.get_bool('flag_wx_emoj', cm.SECTION_MAIN, False))

        self._v['app_path'].set(c.get('app_path', cm.SECTION_RUNTIME))
        self._v['run_mode'].set(c.get('run_mode', cm.SECTION_RUNTIME, 'daemon'))
        self._v['health_port'].set(c.get('health_port', cm.SECTION_RUNTIME, '0'))
        self._v['keep_awake'].set(c.get_bool('keep_awake', cm.SECTION_RUNTIME, True))
        self._v['watchdog'].set(c.get_bool('watchdog', cm.SECTION_RUNTIME, True))
        # 自启动以系统真实状态为准，避免与注册表不一致
        try:
            auto_enabled, _ = autostart.status()
        except Exception:
            auto_enabled = c.get_bool('autostart', cm.SECTION_RUNTIME, False)
        self._v['autostart'].set(auto_enabled)
        self._v['watchdog_interval'].set(
            c.get('watchdog_interval', cm.SECTION_RUNTIME, '5'))
        self._v['max_restarts_per_hour'].set(
            c.get('max_restarts_per_hour', cm.SECTION_RUNTIME, '20'))

        info = cm.platform_info()
        text = ('  系统: %s (%s)   Python: %s\n'
                '  打包运行: %s\n'
                '  微信自动化: %s' % (
                    info['os_name'], info['arch'], info['python'],
                    '是' if info['frozen'] else '否（源码运行）',
                    '支持（Windows）' if info['automation_supported']
                    else '不支持（仅 Windows 可用，其他平台只能打包 UI 与守护层）'))
        self.runtime_info.set(text)

        self._sync_editor_state()

    def _sync_editor_state(self):
        mode = self._v['t_mode'].get()
        if mode == 'dict':
            self.ent_content.configure(state='disabled')
            self.cb_dict.configure(state='readonly')
        else:
            self.ent_content.configure(state='normal')
            self.cb_dict.configure(state='disabled')

    def _collect(self):
        c = self.cfg
        for key in ('my_lady_wechat_name', 'say_good_morning', 'say_good_lunch',
                    'say_good_dinner', 'say_good_dream', 'birthday_month',
                    'birthday_day'):
            c.set(key, self._v[key].get().strip())

        c.set('silent_mode', '1' if self._v['silent_mode'].get() else '0')
        c.set('flag_learn_english', '1' if self._v['flag_learn_english'].get() else '0')
        c.set('flag_wx_emoj', '1' if self._v['flag_wx_emoj'].get() else '0')

        c.set('app_path', self._v['app_path'].get().strip(), cm.SECTION_RUNTIME)
        c.set('run_mode', self._v['run_mode'].get(), cm.SECTION_RUNTIME)
        c.set('health_port', self._v['health_port'].get().strip(), cm.SECTION_RUNTIME)
        c.set('keep_awake', '1' if self._v['keep_awake'].get() else '0',
              cm.SECTION_RUNTIME)
        c.set('watchdog', '1' if self._v['watchdog'].get() else '0',
              cm.SECTION_RUNTIME)
        c.set('autostart', '1' if self._v['autostart'].get() else '0',
              cm.SECTION_RUNTIME)
        c.set('watchdog_interval',
              self._v['watchdog_interval'].get().strip() or '5',
              cm.SECTION_RUNTIME)
        c.set('max_restarts_per_hour',
              self._v['max_restarts_per_hour'].get().strip() or '20',
              cm.SECTION_RUNTIME)
        c.set_tasks(self.tasks)

    def on_save(self):
        self._collect()
        errors = self.cfg.validate()
        if errors:
            messagebox.showerror('配置有误', '\n'.join(errors), parent=self)
            return

        try:
            self.cfg.save()
        except OSError as e:
            messagebox.showerror('保存失败', str(e), parent=self)
            return

        try:
            msg = autostart.sync(self.cfg.get_bool('autostart', cm.SECTION_RUNTIME))
        except Exception as e:
            msg = '自启动同步失败: %s' % e

        self.status_var.set('已保存 %s · %s' % (self.cfg.path, msg))
        messagebox.showinfo('保存成功', '配置已写入:\n%s\n\n%s'
                            % (self.cfg.path, msg), parent=self)

    # ------------------------------------------------------------------
    # 任务表操作
    # ------------------------------------------------------------------
    def _refresh_task_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for t in self.tasks:
            content = (t['content'] if t['mode'] == 'custom'
                       else '[字典] ' + t.get('dict', ''))
            self.tree.insert('', 'end', values=(
                t['time'], MODE_LABELS.get(t['mode'], t['mode']),
                content, t['receiver']))

    def _on_task_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx >= len(self.tasks):
            return
        t = self.tasks[idx]
        self._v['t_time'].set(t['time'])
        self._v['t_mode'].set(t['mode'])
        self._v['t_content'].set(t['content'])
        self._v['t_dict'].set(t.get('dict') or 'all')
        self._v['t_receiver'].set(t['receiver'])
        self._sync_editor_state()

    def _editor_task(self):
        mode = self._v['t_mode'].get()
        task = {
            'time': self._v['t_time'].get().strip(),
            'mode': mode,
            'content': self._v['t_content'].get().strip() if mode == 'custom' else '',
            'dict': self._v['t_dict'].get() if mode == 'dict' else '',
            'receiver': self._v['t_receiver'].get().strip()
                        or self._v['my_lady_wechat_name'].get().strip(),
        }
        if not cm.TIME_RE.match(task['time']) or task['time'] == '99:99':
            messagebox.showerror('时间格式错误', '请输入 HH:MM（如 08:30）', parent=self)
            return None
        if mode == 'custom' and not task['content']:
            messagebox.showerror('内容为空', '自定义模式必须填写内容', parent=self)
            return None
        return task

    def on_task_add(self):
        task = self._editor_task()
        if task is None:
            return
        self.tasks.append(task)
        self._refresh_task_tree()
        self.status_var.set('已添加任务（尚未保存到文件）')

    def on_task_update(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo('提示', '请先在列表中选中一行', parent=self)
            return
        task = self._editor_task()
        if task is None:
            return
        self.tasks[self.tree.index(sel[0])] = task
        self._refresh_task_tree()

    def on_task_delete(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo('提示', '请先在列表中选中一行', parent=self)
            return
        del self.tasks[self.tree.index(sel[0])]
        self._refresh_task_tree()

    # ------------------------------------------------------------------
    # 运行控制
    # ------------------------------------------------------------------
    def _pick_app(self):
        path = filedialog.askopenfilename(
            parent=self, title='选择要守护的应用',
            filetypes=[('可执行文件', '*.exe'), ('Python 脚本', '*.py'),
                       ('所有文件', '*.*')])
        if path:
            self._v['app_path'].set(path)

    def on_start(self):
        self._collect()
        errors = self.cfg.validate()
        if errors:
            messagebox.showerror('配置有误', '\n'.join(errors), parent=self)
            return
        self.cfg.save()
        import launcher
        launcher.CONFIG_PATH = self.cfg.path
        rc = launcher.cmd_start()
        self._refresh_status()
        if rc == 0:
            messagebox.showinfo('已启动', '后台守护进程已启动', parent=self)
        else:
            messagebox.showwarning('启动异常', '请用 launcher.py daemon 前台排查', parent=self)

    def on_stop(self):
        import launcher
        launcher.CONFIG_PATH = self.cfg.path
        launcher.cmd_stop()
        self._refresh_status()

    def _refresh_status(self):
        pid = sp.read_pid(os.path.join(cm.app_dir(), 'run.pid'))
        alive = sp.pid_alive(pid)
        auto_on, _ = autostart.status()
        self.status_var.set('后台: %s    PID: %s    开机自启: %s' % (
            '运行中' if alive else '未运行',
            pid if pid else '-',
            '开' if auto_on else '关'))


def run_ui(config_path=None):
    # 高 DPI 适配（Windows 下避免界面模糊）
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = ConfigWindow(config_path)
    app.mainloop()


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else None
    run_ui(path)
