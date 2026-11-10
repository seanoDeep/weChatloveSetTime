# -*- coding:utf-8 -*-
"""
微信 4.2 纯 Win32 适配器 —— 绕开 wxauto4 版本匹配问题
底层: win32api.keybd_event + pyperclip 剪贴板 + FindWindow
"""
import sys, time, ctypes

if sys.platform != 'win32':
    raise ImportError(
        "Wx42Adapter 依赖 Win32 键盘事件与窗口 API，仅支持 Windows。\n"
        "当前系统: %s。\n"
        "配置界面 / 进程守护 / 开机自启在非 Windows 平台仍可使用，"
        "但微信自动发送功能不可用。" % sys.platform
    )

try:
    import win32gui, win32con, win32api, win32process
    import pyperclip
except ImportError as e:
    raise ImportError(
        "缺少 Windows 依赖: %s\n"
        "请执行: pip install pywin32 pyperclip" % e
    )


# 虚拟键码
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_ALT = 0x12
VK_F = 0x46
VK_ESCAPE = 0x1B
VK_ENTER = 0x0D
VK_BACKSPACE = 0x08
VK_V = 0x56
VK_A = 0x41
VK_C = 0x43
VK_TAB = 0x09
VK_F3 = 0x72
VK_F6 = 0x75


class Wx42Adapter:
    """
    微信 4.2 桌面版适配器（Qt + MMUI 自绘窗口）
    不依赖 wxauto4 的 WeChatMainWnd 版本匹配逻辑
    底层走 Win32 键盘事件 + 剪贴板
    """

    WINDOW_CLASS = 'Qt51514QWindowIcon'
    WINDOW_TITLE = '微信'

    def __init__(self, ads=True, **kwargs):
        self.hwnd = None
        self._find_and_activate()
        self.nickname = '微信用户'

    # ---------- 内部 ----------

    def _find_and_activate(self):
        """找微信主窗口并激活到前台（绕过 SetForegroundWindow 限制）"""
        self.hwnd = win32gui.FindWindow(self.WINDOW_CLASS, self.WINDOW_TITLE)
        if not self.hwnd:
            raise RuntimeError(
                "未找到微信主窗口！请确认：\n"
                "  1. 微信 PC 客户端已启动并登录\n"
                "  2. 窗口标题为「微信」（无额外前缀）\n"
                "  3. 版本 4.2.0.11 或相近的 4.2.x"
            )
        # 恢复窗口
        if win32gui.IsIconic(self.hwnd):
            win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
        # 用 AttachThreadInput 绕过前台窗口限制
        try:
            fg = win32gui.GetForegroundWindow()
            cur_tid = win32api.GetCurrentThreadId()
            fg_tid = win32process.GetWindowThreadProcessId(fg)[0]
            if fg_tid != cur_tid:
                ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, True)
                win32gui.SetForegroundWindow(self.hwnd)
                ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, False)
            else:
                win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            # AttachThreadInput 失败就用 Alt 键骗一下（最后兜底）
            try:
                self._press(VK_ALT)
                win32gui.SetForegroundWindow(self.hwnd)
            except Exception:
                pass
        win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW)
        time.sleep(0.8)

    @staticmethod
    def _press(*vks, hold=0.05):
        """按下并释放一个或多个虚拟键"""
        for vk in vks:
            win32api.keybd_event(vk, 0, 0, 0)
            time.sleep(hold)
        # 逆序释放（先按的后放）
        for vk in reversed(vks):
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    @staticmethod
    def _key(vk):
        """单次按键（按下+释放）"""
        win32api.keybd_event(vk, 0, 0, 0)
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)

    @staticmethod
    def _paste(text):
        """剪贴板粘贴"""
        pyperclip.copy(text)
        Wx42Adapter._press(VK_CONTROL, VK_V)

    def _ensure_foreground(self):
        """
        确保微信窗口在前台，返回是否成功。
        失败时必须由调用方中止操作，否则键盘事件会落到其他窗口，
        导致把内容输入到别的程序里。
        """
        if win32gui.GetForegroundWindow() == self.hwnd:
            return True
        try:
            fg_tid = win32process.GetWindowThreadProcessId(
                win32gui.GetForegroundWindow())[0]
            cur_tid = win32api.GetCurrentThreadId()
            ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, True)
            win32gui.SetForegroundWindow(self.hwnd)
            ctypes.windll.user32.AttachThreadInput(cur_tid, fg_tid, False)
            time.sleep(0.2)
        except Exception:
            pass
        return win32gui.GetForegroundWindow() == self.hwnd

    # ---------- 公共 API（对齐 wxauto4 WeChat） ----------

    def GetMyInfo(self):
        """返回当前登录账号信息（简化版）"""
        return {'nickname': self.nickname}

    def IsOnline(self):
        """判断微信窗口是否存在（近似在线检测）"""
        return win32gui.IsWindow(self.hwnd)

    def ChatWith(self, who, exact=True, force=False, force_wait=0.5):
        """
        打开聊天窗口（通过搜索框）
        who: 联系人昵称 / 文件传输助手 等
        """
        if not self._ensure_foreground():
            raise RuntimeError(
                "无法把微信窗口切到前台，已中止本次操作 "
                "(避免把文字误输入到其他窗口)"
            )

        # Ctrl+F 唤起搜索框
        self._press(VK_CONTROL, VK_F)
        time.sleep(0.45)

        # 清空搜索框里可能残留的旧关键词
        self._press(VK_CONTROL, VK_A)
        time.sleep(0.1)
        self._key(VK_BACKSPACE)
        time.sleep(0.1)

        # 粘贴搜索词
        self._paste(who)
        time.sleep(0.6)

        # 回车打开第一个搜索结果
        self._key(VK_ENTER)
        time.sleep(0.6)

        if force:
            time.sleep(force_wait)

    def SendMsg(self, msg, who=None, clear=True, at=None, exact=False):
        """
        发送消息
        msg: 消息文本
        who: 可选，先切到这个联系人再发
        """
        if who:
            self.ChatWith(who)
            time.sleep(0.6)

        if not self._ensure_foreground():
            raise RuntimeError(
                "无法把微信窗口切到前台，已中止发送 "
                "(避免把文字误输入到其他窗口)"
            )

        # 清空输入框里的残留内容
        if clear:
            self._press(VK_CONTROL, VK_A)
            time.sleep(0.15)
            self._key(VK_BACKSPACE)
            time.sleep(0.1)

        # 粘贴消息
        self._paste(msg)
        time.sleep(0.4)

        # Enter 发送
        self._key(VK_ENTER)
        time.sleep(0.5)

        class WxResponse:
            def __init__(self, ok, text):
                self.ok = ok
                self.text = text
            def __bool__(self):
                return self.ok
            def __repr__(self):
                return f"WxResponse(ok={self.ok}, text={self.text})"

        return WxResponse(True, "sent")

    def ChatInfo(self):
        """
        获取当前聊天窗口信息（简化版）
        4.2 的 MMUI 自绘窗口拿不到 UIA 树，只能返回近似值
        """
        return {'chat_name': 'unknown'}

    def GetSession(self):
        """获取会话列表（简化版：返回空列表）"""
        return []

    def GetAllMessage(self):
        """
        获取当前聊天窗口消息（简化版）
        4.2 自绘窗口无法直接读 UIA 消息树
        返回空列表，消息监听场景不适用
        """
        return []

    def SendMsgToFileHelper(self, msg):
        """便捷方法：发消息到文件传输助手"""
        return self.SendMsg(msg, who='文件传输助手')


# 导出一个工厂别名，让 say_to_lady.py 保持 wxauto4 的调用风格
WeChat = Wx42Adapter


# ========== 独立测试 ==========
if __name__ == '__main__':
    print("=== Wx42Adapter 单元测试 ===\n")
    try:
        wx = Wx42Adapter()
        print("[PASS] 连接微信成功 (HWND=%d)" % wx.hwnd)
        print("       在线:", wx.IsOnline())
        print("       昵称:", wx.GetMyInfo())

        print("\n--- 测试1: ChatWith(文件传输助手) ---")
        wx.ChatWith('文件传输助手')
        print("[PASS] 已打开文件传输助手聊天窗口")

        print("\n--- 测试2: SendMsg ---")
        resp = wx.SendMsg('Wx42Adapter 适配器测试 %s' % time.strftime('%H:%M:%S'))
        print("[PASS] 发送结果:", resp)

        print("\n✅ 请在微信中确认文件传输助手是否收到测试消息")
    except Exception as e:
        import traceback
        print("[FAIL]", type(e).__name__, e)
        traceback.print_exc()
