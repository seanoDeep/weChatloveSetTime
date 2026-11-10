# 微信守护女友 · 定时问候与进程守护

> 每天在指定时间通过微信桌面端自动发送问候，附带可视化配置、进程守护、开机自启与一键打包。
> 底层已从「网页版协议」迁移到「微信 PC 客户端 UI 自动化」，适配微信 4.2.x。

---

## 功能特性

| 能力 | 说明 |
| --- | --- |
| 每日定时问候 | 起床 / 午饭 / 晚饭 / 睡觉四个时段，时间到点自动发送 |
| 自定义定时任务 | 任意多组时间点，内容可手写，也可从内置句子库随机抽取 |
| 节日与生日祝福 | 情人节、妇女节、平安夜、圣诞节、生日自动发送 |
| 静默模式 | 完全不输出控制台日志，后台无感知运行 |
| 可视化配置窗口 | tkinter 图形界面，改完保存即生效 |
| 进程守护 | 子进程崩溃或被结束后自动重启，带回退与频率限制 |
| 后台保活 | Windows 下阻止系统休眠回收进程 |
| 开机自启动 | Windows 注册表 / macOS LaunchAgent / Linux autostart |
| 健康检查 | 本地 HTTP 接口查看运行状态、重启次数 |
| 一键打包 | PyInstaller 双目标产物，约 14 MB / 17 MB |

---

## 环境要求

- **系统**：Windows 10/11（微信自动化仅 Windows 可用）
- **Python**：3.8+
- **微信**：PC 客户端 4.2.x，且已登录、窗口标题为「微信」
- **权限**：脚本与微信客户端需处于相同权限级别（都普通 / 都管理员）

### 安装依赖

```powershell
pip install pywin32 pyperclip requests
# 可选：更精确的进程检测
pip install psutil
# 可选：打包
pip install pyinstaller
```

---

## 快速开始

### 1. 配置

**方式 A：图形界面（推荐）**

```powershell
python launcher.py ui
```

打开后有三个页签：

- **基础设置**：女友微信昵称、四个问候时间、生日、静默 / 学英语 / 表情开关
- **自定义任务**：添加任意时间点的发送任务
- **运行与系统**：应用路径、健康检查端口、运行模式、守护、开机自启

点击「保存配置」写入 `config.ini`，勾选「开机自启动」时会同步写入系统。

**方式 B：直接编辑 `config.ini`**

```ini
[configuration]
my_lady_wechat_name = 小强子
silent_mode = 0

birthday_month = 03
birthday_day = 18

say_good_morning = 07:30
say_good_lunch = 12:00
say_good_dinner = 18:30
say_good_dream = 23:00

flag_learn_english = 1
flag_wx_emoj = 1
```

> 时间必须是**补零的 24 小时制 `HH:MM`**（如 `08:30`），`99:99` 表示该时段不启用。

### 2. 运行

```powershell
# 前台运行，便于观察日志
python launcher.py run

# 后台静默启动（推荐日常使用）
python launcher.py start

# 查看状态
python launcher.py status

# 停止
python launcher.py stop
```

启动前请确认微信 PC 客户端已登录，且窗口未被最小化到托盘。

---

## 命令行说明

| 命令 | 作用 |
| --- | --- |
| `python launcher.py ui` | 打开可视化配置窗口 |
| `python launcher.py run` | 前台运行，不启用进程守护 |
| `python launcher.py daemon` | 前台运行守护模式（便于排查） |
| `python launcher.py start` | 后台启动守护进程，无窗口 |
| `python launcher.py stop` | 停止后台守护进程（含子进程） |
| `python launcher.py status` | 查看运行状态、自启状态、任务数量 |
| `python launcher.py autostart on\|off\|status` | 开机自启动管理 |
| `python launcher.py build` | PyInstaller 打包 |

所有命令都支持 `--config <路径>` 指定其它配置文件。

---

## 配置文件结构

### `[configuration]` 基础参数

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `my_lady_wechat_name` | 空 | 女友微信**昵称**（不是微信号 / 备注） |
| `silent_mode` | `0` | `1` = 完全不输出控制台日志 |
| `birthday_month` / `birthday_day` | `99` | 生日，`99` 表示不启用 |
| `say_good_morning` 等四项 | `99:99` | 四个问候时间点 |
| `flag_learn_english` | `0` | 睡觉问候是否附带每日英语 |
| `flag_wx_emoj` | `0` | 结尾是否追加随机颜文字 |
| `str_Valentine` 等五项 | — | 节日与生日祝福语 |

### `[custom_tasks]` 自定义任务

每个任务用 `taskN_*` 描述，编号从 1 开始：

```ini
[custom_tasks]
task1_time     = 10:30
task1_mode     = custom
task1_content  = 记得多喝水呀~
task1_receiver = 小强子

task2_time     = 20:00
task2_mode     = dict
task2_dict     = all
task2_receiver = 文件传输助手
```

| 字段 | 取值 |
| --- | --- |
| `time` | `HH:MM`，24 小时制补零 |
| `mode` | `custom` 手写内容 / `dict` 从句子库随机 |
| `content` | `mode=custom` 时必填 |
| `dict` | `morning` / `lunch` / `dinner` / `dream` / `emoj` / `all` |
| `receiver` | 接收人昵称，缺省为女友昵称 |

### `[runtime]` 运行参数（由 UI 维护）

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `app_path` | 空 | 要守护的应用；留空使用内置 `say_to_lady.py` |
| `run_mode` | `daemon` | `daemon` 后台 / `console` 前台 |
| `health_port` | `0` | 本地健康检查端口，`0` 不启用 |
| `keep_awake` | `1` | 阻止系统休眠回收 |
| `watchdog` | `1` | 异常退出自动重启 |
| `watchdog_interval` | `5` | 子进程存活轮询间隔（秒） |
| `max_restarts_per_hour` | `20` | 每小时重启上限，超出后降速 |
| `autostart` | `0` | 开机自启（保存配置时同步到系统） |

---

## 进程守护与保活

守护模式的结构：

```
launcher.py daemon
  └── Supervisor          # 轮询子进程状态
        └── say_to_lady.py  # 业务进程
```

- 子进程异常退出后按 **指数退避** 重启（2s → 4s → 8s …，上限 60s）
- 每小时重启次数超过 `max_restarts_per_hour` 时，改为每 5 分钟尝试一次
- `keep_awake = 1` 时调用 `SetThreadExecutionState` 阻止系统休眠
- 配置了 `health_port` 后，可访问：

```powershell
curl http://127.0.0.1:8899/health
# {"status":"running","pid":1234,"uptime":3600,"starts":3,"restarts":2,"crashes":2,"child_alive":true}
```

**开机自启** 写入位置：

- Windows：`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 的 `SayToLady`
- macOS：`~/Library/LaunchAgents/com.saytolady.agent.plist`
- Linux：`~/.config/autostart/say-to-lady.desktop`

---

## 打包

```powershell
python build.py            # 单文件，生成两个 exe
python build.py --onedir   # 目录模式，启动更快
python build.py --console  # 保留控制台，便于排查
python build.py --clean    # 打包前清理 build/dist
```

产物：

| 文件 | 体积 | 用途 |
| --- | --- | --- |
| `dist/SayToLady.exe` | ≈ 13.7 MB | 统一入口：`ui` / `run` / `daemon` / `start` / `stop` / `status` |
| `dist/SayToLadyConfig.exe` | ≈ 16.6 MB | 直接打开配置窗口 |

首次运行会在 exe 同级目录自动生成 `config.ini` 与 `remind_sentence/`，之后所有配置都读写该目录，可直接整体拷贝分发。

> 若公司电脑启用了 Application Control 策略，未签名的 exe 可能被拦截，需要在允许的环境或白名单中运行。

---

## 工作原理

```
launcher.py  ──读取──>  config.ini
     │
     ├─ 调度：每 10 秒轮询一次（时间误差 ≤ 1 分钟）
     │        按 (日期, 时段) 去重，同一天同一时段只发一次
     │
     └─ 发送：wx42_adapter.Wx42Adapter
               FindWindow('Qt51514QWindowIcon', '微信')
               └ AttachThreadInput 抢前台
               └ Ctrl+F 搜索联系人 → 粘贴 → 回车
               └ Ctrl+A 清空输入框 → 粘贴内容 → 回车发送
```

为什么不继续用 `itchat` / `wxpy`：

1. 微信自 2017 年起逐步封禁网页版登录，返回的是 HTML 拒绝页，`itchat` 强行按 XML 解析，于是抛出 `ExpatError: mismatched tag: line 64, column 4`。
2. 微信 4.0.6+ 关闭了 Chromium Accessibility 导出，`wxauto` 免费版依赖的 UIA 控件树失效，主窗口下只剩自绘的 `MMUIRenderSubWindow`。
3. 因此改为纯 Win32 键盘事件 + 剪贴板，不碰协议、不注入进程，只模拟人工操作。

---

## 目录结构

```
A_01/
├── say_to_lady.py       业务主逻辑：配置读取、调度、发送
├── wx42_adapter.py      微信 4.2 适配层（Win32 + 剪贴板）
├── config.ini           唯一配置文件
├── config_manager.py    配置读写 / 校验 / 打包后资源释放
├── ui_config.py         可视化配置窗口
├── launcher.py          统一启动入口
├── supervisor.py        进程守护 + 防止休眠
├── autostart.py         开机自启动（跨平台）
├── build.py             PyInstaller 打包脚本
├── remind_sentence/     四个时段的句子库（可自行增删）
├── tests/test_features.py  全流程测试
└── dist/                打包产物
```

---

## 测试

```powershell
python tests/test_features.py
```

覆盖 18 项：

- 配置默认值、读写往返、字段校验、自定义任务增删
- 开机自启（dry-run，不写真实注册表）
- `KeepAwake` 获取与释放、Supervisor 是否真正挂载
- 进程守护：子进程崩溃后自动重启、PID 文件读写
- 调度回归：多任务同分钟触发、自定义内容、字典内容、静默模式零输出
- 配置文件驱动的 `taskN_*` 解析
- 平台信息探测、可视化窗口的载入与保存逻辑

---

## 已知限制

1. **仅 Windows 可自动发送**。`wx42_adapter` 依赖 Win32 键盘与窗口 API，macOS / Linux 上会给出明确报错。配置窗口、进程守护、开机自启在 macOS / Linux 仍可使用。
2. **需要微信窗口可被激活**。发送时会短暂抢占前台，若正在全屏游戏或远程桌面断开，可能失败。
3. **不支持读取聊天记录**。微信 4.2 聊天区为自绘窗口，无法通过 UIA 读取消息，因此没有「女友消息监听 / 情感分析」功能。
4. **发送依赖剪贴板**，会覆盖当前剪贴板内容。
5. **不含历史时段的补发**：若在某个时间点之后才启动，当天该时段不会补发。

---

## 常见问题

**Q：提示「未找到微信主窗口」？**
确认微信已登录且窗口标题为「微信」；若版本不是 4.2，可在 `wx42_adapter.py` 顶部调整 `WINDOW_CLASS` / `WINDOW_TITLE`。

**Q：到点了但没发出去？**
先看 `python launcher.py status` 是否在运行；再确认时间格式补零（`8:30` 无效，`08:30` 有效）；最后确认微信窗口未被最小化。

**Q：文字被输入到别的程序里了？**
旧版本在前台切换失败时会继续发送。现在 `_ensure_foreground()` 失败会直接抛异常中止，不会误输入。若仍出现，请检查是否有全屏程序抢占焦点。

**Q：仍然看到 `ExpatError: mismatched tag`？**
说明还在使用 `itchat` / `wxpy`。本项目已不再依赖这两个库，请确认执行的是 `launcher.py` 或 `say_to_lady.py`。

---

## License

[The MIT License (MIT)](http://opensource.org/licenses/MIT)
