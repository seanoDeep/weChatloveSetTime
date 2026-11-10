# -*- coding:utf-8 -*-
"""
微信守护女友脚本 —— 定时发送 / 自定义任务 / 静默模式
底层: Wx42Adapter (Win32 键盘事件 + 剪贴板)，兼容微信 PC 客户端 4.2.x

配置文件: config.ini
  [configuration]        女友昵称 / 问候时间 / 节日祝福 / 开关
  [custom_tasks]         自定义定时任务
  [runtime]              运行参数（由 UI 配置窗口维护）

本模块既可 `python say_to_lady.py` 直接运行，也可被 launcher.py 以
`say_to_lady.main()` 方式调用（打包为单文件 exe 时使用）。
"""
from __future__ import unicode_literals
from wx42_adapter import WeChat
from requests import get
from random import choice
from threading import Thread
import configparser
import os
import re
import sys
import time
import logging

TASK_KEY_RE = re.compile(r'^task(\d+)[._]([a-z]+)$')


# ---------------------------------------------------------------------------
# 路径解析：兼容源码运行与 PyInstaller 冻结运行
# ---------------------------------------------------------------------------
def base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = base_dir()
CONFIG_PATH = os.path.join(BASE_DIR, 'config.ini')
SENTENCE_DIR = os.path.join(BASE_DIR, 'remind_sentence')


# ---------------------------------------------------------------------------
# 日志控制
# ---------------------------------------------------------------------------
silent_mode = False


def _log(msg=""):
    """统一的日志出口：silent_mode=True 时完全 no-op"""
    if silent_mode:
        return
    print(msg, flush=True)


logging.getLogger('wxauto').setLevel(logging.WARNING)


def get_message():
    """获取每日励志精句（超时降级）"""
    r = get("http://open.iciba.com/dsapi/", timeout=8)
    note = r.json()['note']
    content = r.json()['content']
    return note, content


# ---------------------------------------------------------------------------
# 发送层
# ---------------------------------------------------------------------------
def send_message(your_message, target_name=None):
    """
    发送消息给指定联系人
    target_name: 默认 my_lady_wechat_name；None 时发文件传输助手
    返回是否成功
    """
    target = target_name or my_lady_wechat_name
    try:
        wx.ChatWith(target)
        wx.SendMsg(your_message)
        return True
    except Exception as e:
        error_msg = u"守护女友出问题了，赶紧去看看咋回事~ 错误: %s" % str(e)
        _log(error_msg)
        try:
            wx.ChatWith('文件传输助手')
            wx.SendMsg(error_msg)
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# 自定义任务解析
# ---------------------------------------------------------------------------
def parse_custom_tasks(cf, dict_pools):
    """从 [custom_tasks] 解析任务，返回 list[dict]"""
    tasks = []
    if not cf.has_section('custom_tasks'):
        return tasks

    # 按 taskN 聚合，例如 task1_time / task1_mode / task1_content
    buckets = {}
    for key, value in cf.items('custom_tasks'):
        m = TASK_KEY_RE.match(key.lower())
        if m:
            buckets.setdefault(int(m.group(1)), {})[m.group(2)] = value

    for tid in sorted(buckets):
        bucket = buckets[tid]

        t_time = (bucket.get('time') or '').strip()
        if not t_time or len(t_time) != 5 or t_time[2] != ':':
            _log("[自定义任务 %s] time 字段缺失或格式错误 (应为 HH:MM)，已跳过" % tid)
            continue

        t_mode = (bucket.get('mode') or 'custom').strip().lower()
        t_content = bucket.get('content', '') or ''
        t_dict = (bucket.get('dict') or '').strip().lower()
        t_receiver = (bucket.get('receiver') or my_lady_wechat_name).strip()

        if t_mode == 'custom' and not t_content.strip():
            _log("[自定义任务 %s] mode=custom 但未提供 content，已跳过" % tid)
            continue
        if t_mode == 'dict' and t_dict not in dict_pools:
            _log("[自定义任务 %s] dict=%s 不是有效的字典键，已跳过" % (tid, t_dict))
            continue

        tasks.append({
            'id': int(tid),
            'time': t_time,
            'mode': t_mode,
            'content': t_content,
            'dict_key': t_dict,
            'receiver': t_receiver,
        })

    return tasks


# ---------------------------------------------------------------------------
# 调度核心
# ---------------------------------------------------------------------------
def build_schedule(dict_pools, custom_tasks):
    """组装完整调度表（原有 4 时段 + 节日 + 自定义任务）"""
    schedule = []

    daily = [
        ('morning', say_good_morning, dict_pools['morning'], '提醒女友早上起床'),
        ('lunch',   say_good_lunch,   dict_pools['lunch'],   '提醒女友中午吃饭'),
        ('dinner',  say_good_dinner,  dict_pools['dinner'],  '提醒女友晚上吃饭'),
        ('dream',   say_good_dream,   dict_pools['dream'],   '提醒女友晚上睡觉'),
    ]
    for slot_id, hm, pool, desc in daily:
        schedule.append({
            'slot_id': slot_id,
            'time': hm,
            'day_filter': None,
            'builder': _make_daily_builder(slot_id, pool),
            'receiver': my_lady_wechat_name,
            'log_text': desc,
        })

    festival = [
        ('valentine', '02', '14', '08:00', str_Valentine, '发送情人节祝福'),
        ('women', '03', '08', '08:00', str_Women, '发送三八妇女节祝福'),
        ('christmas_eve', '12', '24', '00:00', str_Christmas_Eve, '发送平安夜祝福'),
        ('christmas', '12', '25', '00:00', str_Christmas, '发送圣诞节祝福'),
        ('birthday', birthday_month, birthday_day, '00:00',
         str_birthday, '发送生日祝福'),
    ]
    for slot_id, m, d, hm, text, desc in festival:
        schedule.append({
            'slot_id': slot_id,
            'time': hm,
            'day_filter': (m, d),
            'builder': lambda text=text: text,
            'receiver': my_lady_wechat_name,
            'log_text': desc,
        })

    for t in custom_tasks:
        if t['mode'] == 'custom':
            builder = lambda c=t['content']: c
        else:
            pool_key = t['dict_key']
            if pool_key == 'all':
                all_pool = (dict_pools['morning'] + dict_pools['lunch']
                            + dict_pools['dinner'] + dict_pools['dream'])
            elif pool_key == 'emoj':
                all_pool = dict_pools['emoj']
            else:
                all_pool = dict_pools.get(pool_key, [])
            builder = lambda p=all_pool: choice(p).strip() if p else ''

        schedule.append({
            'slot_id': 'custom_%d' % t['id'],
            'time': t['time'],
            'day_filter': None,
            'builder': builder,
            'receiver': t['receiver'],
            'log_text': '执行自定义任务 %d' % t['id'],
        })

    return schedule


def _make_daily_builder(slot_id, pool):
    """原有 4 个时段的消息构造逻辑"""
    def builder():
        msg = choice(pool).strip()
        if slot_id == 'dream' and flag_learn_english:
            try:
                note, content = get_message()
                msg = (msg + "\n\n" + "顺便一起来学英语哦：\n"
                       + "原文: " + content + "\n\n翻译: " + note)
            except Exception as e:
                _log("[每日学英语获取失败，本条改为纯问候] %s" % str(e))
        if flag_wx_emoj:
            msg = msg + choice(str_list_emoj)
        return msg
    return builder


def run_schedule(schedule):
    """统一调度主循环：每 10 秒检查一次，命中后发送并当日去重"""
    fired = set()

    while True:
        try:
            now = time.localtime()
            today = time.strftime('%Y-%m-%d', now)
            today_md = (time.strftime('%m', now), time.strftime('%d', now))
            now_hm = time.strftime('%H:%M', now)

            fired = {item for item in fired if item[0] == today}

            if not silent_mode and now_hm != getattr(run_schedule, '_last_hm', None):
                _log("守护中，时间:%s" % time.ctime())
                run_schedule._last_hm = now_hm

            for item in schedule:
                if now_hm != item['time']:
                    continue
                if (item['day_filter'] is not None
                        and item['day_filter'] != today_md):
                    continue
                key = (today, item['slot_id'])
                if key in fired:
                    continue

                fired.add(key)
                try:
                    msg = item['builder']()
                except Exception as e:
                    _log("[%s] 构造消息时异常: %s" % (item['log_text'], str(e)))
                    continue

                if not msg:
                    _log("[%s] 消息为空，跳过" % item['log_text'])
                    continue

                if send_message(msg, item['receiver']):
                    _log("%s:%s" % (item['log_text'], time.ctime()))

        except Exception as e:
            _log("[守护循环异常，已跳过本轮] %s" % str(e))

        time.sleep(10)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    global silent_mode, wx
    global my_lady_wechat_name
    global say_good_morning, say_good_lunch, say_good_dinner, say_good_dream
    global birthday_month, birthday_day
    global str_Valentine, str_Women, str_Christmas_Eve, str_Christmas, str_birthday
    global flag_learn_english, flag_wx_emoj, str_list_emoj

    # 打包运行首次启动时，确保 config.ini / remind_sentence 已落到 exe 同级目录
    try:
        import config_manager as _cm
        _cm.ensure_assets()
    except Exception:
        pass

    cf = configparser.ConfigParser(interpolation=None, strict=False)
    cf.read(CONFIG_PATH, encoding='UTF-8')

    silent_mode = (cf.get("configuration", "silent_mode",
                          fallback="0").strip() == '1')

    my_lady_wechat_name = cf.get("configuration", "my_lady_wechat_name").strip()

    say_good_morning = cf.get("configuration", "say_good_morning").strip()
    say_good_lunch = cf.get("configuration", "say_good_lunch").strip()
    say_good_dinner = cf.get("configuration", "say_good_dinner").strip()
    say_good_dream = cf.get("configuration", "say_good_dream").strip()

    birthday_month = cf.get("configuration", "birthday_month").strip()
    birthday_day = cf.get("configuration", "birthday_day").strip()

    def _read_lines(name):
        path = os.path.join(SENTENCE_DIR, name)
        with open(path, 'r', encoding='UTF-8') as f:
            return [l.strip() for l in f.readlines()]

    str_list_good_morning = _read_lines('sentence_good_morning.txt')
    str_list_good_lunch = _read_lines('sentence_good_lunch.txt')
    str_list_good_dinner = _read_lines('sentence_good_dinner.txt')
    str_list_good_dream = _read_lines('sentence_good_dream.txt')

    dict_pools = {
        'morning': str_list_good_morning,
        'lunch': str_list_good_lunch,
        'dinner': str_list_good_dinner,
        'dream': str_list_good_dream,
        'all': (str_list_good_morning + str_list_good_lunch
                + str_list_good_dinner + str_list_good_dream),
    }

    flag_learn_english = cf.get("configuration", "flag_learn_english",
                                fallback="0").strip() == '1'
    flag_wx_emoj = cf.get("configuration", "flag_wx_emoj",
                          fallback="0").strip() == '1'

    str_emoj = "(•‾̑⌣‾̑•)✧˖°----(๑´ڡ`๑)----(๑¯ิε ¯ิ๑)----(๑•́ ₃ •̀๑)----( ∙̆ .̯ ∙̆ )----(๑˘ ˘๑)----(●′ω`●)----(●･̆⍛･̆●)----ಥ_ಥ----_(:qゝ∠)----(´；ω；`)----( `)3')----Σ((( つ•̀ω•́)つ----╰(*´︶`*)╯----( ´´ิ∀´ิ` )----(´∩｀。)----( ื▿ ื)----(｡ŏ_ŏ)----( •ิ _ •ิ )----ヽ(*΄◞ิ౪◟ิ‵ *)----( ˘ ³˘)----(; ´_ゝ`)----(*ˉ﹃ˉ)----(◍'౪`◍)ﾉﾞ----(｡◝‿◜｡)----(ಠ .̫.̫ ಠ)----(´◞⊖◟`)----(。≖ˇェˇ≖｡)----(◕ܫ◕)----(｀◕‸◕´+)----(▼ _ ▼)----( ◉ืൠ◉ื)----ㄟ(◑‿◐ )ㄏ----(●'◡'●)ﾉ♥----(｡◕ˇ∀ˇ◕）----( ◔ ڼ ◔ )----( ´◔ ‸◔`)----(☍﹏⁰)----(♥◠‿◠)----ლ(╹◡╹ლ )----(๑꒪◞౪◟꒪๑)"
    str_list_emoj = [s for s in str_emoj.split('----') if s]
    dict_pools['emoj'] = str_list_emoj

    str_Valentine = cf.get("configuration", "str_Valentine").strip()
    str_Women = cf.get("configuration", "str_Women").strip()
    str_Christmas_Eve = cf.get("configuration", "str_Christmas_Eve").strip()
    str_Christmas = cf.get("configuration", "str_Christmas").strip()
    str_birthday = cf.get("configuration", "str_birthday").strip()

    custom_tasks = parse_custom_tasks(cf, dict_pools)

    _log("正在连接本机微信客户端...")
    try:
        wx = WeChat(ads=False)
    except Exception as e:
        _log("\n[错误] 连接微信失败: %s" % str(e))
        _log("请确保微信 PC 客户端已启动登录、且与脚本权限级别一致")
        return 1

    schedule = build_schedule(dict_pools, custom_tasks)

    t_sched = Thread(target=run_schedule, args=(schedule,),
                     name='watcher_schedule', daemon=True)
    t_sched.start()

    if not silent_mode:
        _log("\n守护女友已启动！")
        _log("  问候时段: 起床=%s 午饭=%s 晚饭=%s 睡觉=%s" % (
            say_good_morning, say_good_lunch, say_good_dinner, say_good_dream))
        if custom_tasks:
            _log("  自定义任务: %d 个" % len(custom_tasks))
            for ct in custom_tasks:
                mode_txt = ("自定义内容" if ct['mode'] == 'custom'
                            else "从字典[%s]随机" % ct['dict_key'])
                _log("    task%d @ %s → %s (%s)" % (
                    ct['id'], ct['time'], ct['receiver'], mode_txt))
        else:
            _log("  自定义任务: 无")
        _log("  静默模式: 关")
        _log("按 Ctrl+C 退出。\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _log("\n正在退出...守护女友已停止。再见！")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
