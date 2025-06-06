# client_qt/scripts/key_ghost/keyScript.py

import datetime
import random
import time
import win32api
import win32con
import win32gui
import win32process
import psutil
import os
import ctypes
import ctypes.wintypes

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout, QLineEdit, QMessageBox, QComboBox, QRadioButton, QFormLayout
from PySide6.QtCore import Qt, Signal, Slot, QThread, QTimer
from PySide6.QtGui import QDoubleValidator
from jose import jwt, JWTError
from pynput import keyboard

from api_client import ApiClient
from worker import Worker

# --- 配置 ---
WINDOW_TITLE = '按键精灵v1.0.0 - TopUtils'
TOOL_CODE = '2935b71b4381fcb768dac22230869cc'


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", ctypes.wintypes.DWORD), ("wLParam", ctypes.wintypes.WORD), ("wHParam", ctypes.wintypes.WORD))


class INPUT_UNION(ctypes.Union):
    _fields_ = (("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (("type", ctypes.wintypes.DWORD), ("union", INPUT_UNION))


class AutoKeyThread(QThread):
    """后台线程，使用 SendInput 执行自动按键逻辑，避免阻塞GUI。"""

    log_message = Signal(str)

    # --- 将 ctypes 结构体定义为类属性 ---
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    # --- 结构体定义结束 ---

    def __init__(self, hwnd: int, key: str, interval_sec: float, long_press: bool, parent=None):
        super().__init__(parent)
        self.target_hwnd = hwnd
        self.key = key
        self.interval_sec = interval_sec
        self.long_press = long_press
        self._is_running = False

    def _send_key_input(self, vk_code, scan_code, is_key_up=False):
        """使用 SendInput 发送单个按键事件"""
        flags = self.KEYEVENTF_SCANCODE
        if is_key_up:
            flags |= self.KEYEVENTF_KEYUP

        # 现在可以直接访问类中定义的结构体
        inp = INPUT(self.INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_code, wScan=scan_code, dwFlags=flags, time=0, dwExtraInfo=None)))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def run(self):
        """线程主循环"""
        self._is_running = True
        self.log_message.emit(f"线程已启动，模式: {'长按' if self.long_press else '常规'}。")

        try:
            vk_code = win32api.VkKeyScan(self.key)
            scan_code = win32api.MapVirtualKey(vk_code & 0xFF, 0)

            if self.long_press:
                self._send_key_input(vk_code, scan_code, is_key_up=False)
                self.log_message.emit(f"已发送长按保持信号 [KEYDOWN] 到系统。")

            while self._is_running:
                if not self.long_press:
                    self._send_key_input(vk_code, scan_code, is_key_up=False)
                    time.sleep(0.05)
                    self._send_key_input(vk_code, scan_code, is_key_up=True)
                    offset = random.uniform(-0.06, 0.03)
                    sleep_time = max(self.interval_sec + offset, 0.02)
                    self.sleep(int(sleep_time * 1000) / 1000)
                else:
                    self.msleep(100)

        except Exception as e:
            self.log_message.emit(f"[线程错误] {e}")
        finally:
            if self.long_press:
                try:
                    vk_code = win32api.VkKeyScan(self.key)
                    scan_code = win32api.MapVirtualKey(vk_code & 0xFF, 0)
                    self._send_key_input(vk_code, scan_code, is_key_up=True)
                    self.log_message.emit(f"已发送长按释放信号 [KEYUP] 到系统。")
                except Exception as e:
                    self.log_message.emit(f"[错误] 释放按键时出错: {e}")

    def stop(self):
        """请求线程停止"""
        self._is_running = False
        self.log_message.emit("线程停止请求已发送。")


class MainAppPage(QWidget):
    """主应用页面，实现按键精灵功能，并集成授权验证。"""

    # ... 后续的 MainAppPage 代码无需修改 ...
    authorization_required = Signal()
    script_started = Signal()
    script_stopped = Signal()
    hotkey_start_pressed = Signal()
    hotkey_stop_pressed = Signal()

    def __init__(self, email: str, api_client_instance: ApiClient, thread_pool_instance):
        super().__init__()
        self.user_email = email
        self.api = api_client_instance
        self.thread_pool = thread_pool_instance
        self.autokey_thread = None
        self.is_script_active = False
        self.keyboard_hook = None
        self.pressed_keys = set()

        # 授权相关
        self.auth_countdown_timer = QTimer(self)
        self.auth_countdown_timer.timeout.connect(self._update_auth_countdown)
        self.periodic_check_timer = QTimer(self)
        self.periodic_check_timer.timeout.connect(self._perform_periodic_status_check)
        self.current_expire_time_dt = None
        self.remaining_auth_seconds = 0

        # 窗口信息
        self.windows_map = {}
        self.target_hwnd = None

        self._init_ui()
        self._setup_global_hotkeys()
        self.update_window_list()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # 授权和欢迎信息
        self.welcome_label = QLabel(f"授权成功！欢迎您，{self.user_email}")
        font = self.welcome_label.font()
        font.setPointSize(16)
        self.welcome_label.setFont(font)
        self.welcome_label.setAlignment(Qt.AlignCenter)

        self.auth_status_label = QLabel("授权状态：正在初始化...")
        self.auth_status_label.setAlignment(Qt.AlignCenter)
        font_status = self.auth_status_label.font()
        font_status.setPointSize(10)
        self.auth_status_label.setFont(font_status)

        main_layout.addWidget(self.welcome_label)
        main_layout.addWidget(self.auth_status_label)

        # --- 按键精灵原生UI ---
        window_layout = QHBoxLayout()
        window_layout.addWidget(QLabel("目标窗口:"))
        self.window_combo = QComboBox()
        self.window_combo.currentIndexChanged.connect(self.on_window_selected)
        window_layout.addWidget(self.window_combo)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.update_window_list)
        window_layout.addWidget(self.refresh_button)
        main_layout.addLayout(window_layout)

        form_layout = QFormLayout()
        self.key_input = QLineEdit()
        self.key_input.setMaxLength(1)
        self.key_input.setPlaceholderText("例如: w")
        form_layout.addRow("目标按键:", self.key_input)

        self.interval_input = QLineEdit("0.3")
        self.interval_input.setValidator(QDoubleValidator(0.1, 60.0, 2))
        form_layout.addRow("按键频率 (秒):", self.interval_input)

        long_press_layout = QHBoxLayout()
        self.long_press_rb_yes = QRadioButton("是")
        self.long_press_rb_no = QRadioButton("否")
        self.long_press_rb_no.setChecked(True)
        long_press_layout.addWidget(self.long_press_rb_yes)
        long_press_layout.addWidget(self.long_press_rb_no)
        form_layout.addRow("长按模式:", long_press_layout)

        main_layout.addLayout(form_layout)

        self.app_status_label = QLabel("状态：已停止。按 Alt+Q 启动。")
        self.app_status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.app_status_label)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("启动 (Alt+Q)")
        self.stop_button = QPushButton("停止 (Alt+W)")
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        main_layout.addWidget(self.log_output)

        self.start_button.clicked.connect(self.start_script)
        self.stop_button.clicked.connect(self.stop_script)
        self.hotkey_start_pressed.connect(self.start_script)
        self.hotkey_stop_pressed.connect(self.stop_script)
        self.long_press_rb_yes.toggled.connect(lambda checked: self.interval_input.setEnabled(not checked and self.start_button.isEnabled()))

    def _get_visible_windows(self):
        """获取所有可见且有标题的窗口列表"""
        windows = {}
        current_pid = os.getpid()

        def enum_handler(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    title = win32gui.GetWindowText(hwnd)
                    if not title:
                        return
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid == current_pid:
                        return

                    process = psutil.Process(pid)
                    process_name = process.name()
                    if process_name.lower() in {'explorer.exe', 'applicationframehost.exe', 'shellexperiencehost.exe'}:
                        return
                    if win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMINIMIZED:
                        return

                    rect = win32gui.GetWindowRect(hwnd)
                    if (rect[2] - rect[0]) < 100 or (rect[3] - rect[1]) < 100:
                        return

                    display_name = f"{title} [{process_name}]"
                    windows[display_name] = hwnd
                except (psutil.NoSuchProcess, psutil.AccessDenied, win32gui.error):
                    pass

        win32gui.EnumWindows(enum_handler, None)
        return dict(sorted(windows.items()))

    @Slot()
    def update_window_list(self):
        """刷新窗口下拉列表"""
        self.append_log("正在刷新窗口列表...")
        self.window_combo.clear()
        self.windows_map = self._get_visible_windows()
        if not self.windows_map:
            self.append_log("未找到可用窗口。")
            return

        self.window_combo.addItems(self.windows_map.keys())
        self.append_log(f"找到 {len(self.windows_map)} 个可用窗口。")

    @Slot(int)
    def on_window_selected(self, index: int):
        if index == -1:
            self.target_hwnd = None
            return

        selected_text = self.window_combo.itemText(index)
        self.target_hwnd = self.windows_map.get(selected_text)
        if self.target_hwnd:
            self.append_log(f"已选择窗口: '{selected_text}' (句柄: {self.target_hwnd})")
        else:
            self.append_log(f"[警告] 无法找到与 '{selected_text}' 关联的句柄。")

    def _setup_global_hotkeys(self):
        """设置全局热键监听"""

        def on_press(key):
            try:
                if key in {keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}:
                    self.pressed_keys.add(keyboard.Key.alt)
                if hasattr(key, 'char') and key.char:
                    if key.char.lower() == 'q' and keyboard.Key.alt in self.pressed_keys:
                        if self.start_button.isEnabled():
                            self.hotkey_start_pressed.emit()
                    elif key.char.lower() == 'w' and keyboard.Key.alt in self.pressed_keys:
                        if self.stop_button.isEnabled():
                            self.hotkey_stop_pressed.emit()
            except Exception as e:
                self.append_log(f"[热键错误] {e}")

        def on_release(key):
            try:
                if key in {keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}:
                    if keyboard.Key.alt in self.pressed_keys:
                        self.pressed_keys.remove(keyboard.Key.alt)
            except KeyError:
                pass
            except Exception as e:
                self.append_log(f"[热键错误] {e}")

        try:
            self.keyboard_hook = keyboard.Listener(on_press=on_press, on_release=on_release, daemon=True)
            self.keyboard_hook.start()
            self.append_log("全局热键 Alt+Q (启动) 和 Alt+W (停止) 已激活。")
        except Exception as e:
            self.append_log(f"[错误] 无法启动全局热键监听: {e}")
            QMessageBox.warning(self, "热键警告", f"无法启动热键监听: {e}\n请使用界面按钮。")
            self.keyboard_hook = None

    def handle_authorization_status(self, token_data: dict):
        if not token_data:
            self._handle_auth_expiration(message="无法获取授权信息，请重新登录。")
            return

        expire_timestamp = token_data.get('expire_time')
        rest_secs = token_data.get('rest_time')
        reminder = token_data.get('reminder', False)

        if not expire_timestamp or rest_secs is None:
            self._handle_auth_expiration(message="授权信息不完整，请重新登录。")
            return

        try:
            self.current_expire_time_dt = datetime.datetime.fromtimestamp(expire_timestamp)
            self.remaining_auth_seconds = int(rest_secs)
        except (ValueError, TypeError) as e:
            self.append_log(f"解析时间时出错: {e}")
            self._handle_auth_expiration(message="授权时间信息格式错误。")
            return

        if self.remaining_auth_seconds <= 0:
            self._handle_auth_expiration(initial_check=True)
        else:
            self.auth_countdown_timer.start(1000)
            check_interval_ms = min((self.remaining_auth_seconds - 1) * 1000, 15 * 60 * 1000)
            if check_interval_ms > 0:
                self.periodic_check_timer.start(check_interval_ms)
            self._update_auth_status_display(reminder)
            self.append_log(f"授权有效，剩余时间约 {self._format_time(self.remaining_auth_seconds)}。")
            if reminder:
                QMessageBox.warning(self, "授权提醒", "提醒：您的授权即将到期！")

    def _update_auth_status_display(self, reminder: bool):
        time_str = self._format_time(self.remaining_auth_seconds)
        expire_date_str = self.current_expire_time_dt.strftime('%Y-%m-%d %H:%M:%S') if self.current_expire_time_dt else "N/A"
        status_text = f"剩余时间: {time_str} (有效期至: {expire_date_str})"
        if reminder:
            status_text = f"[!] 即将到期！{status_text}"
            self.auth_status_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.auth_status_label.setStyleSheet("color: green;")
        self.auth_status_label.setText(status_text)

    def _format_time(self, seconds):
        seconds = max(0, int(seconds))
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        days, hours = divmod(hours, 24)
        if days > 0:
            return f"{days}天 {hours:02d}:{mins:02d}:{secs:02d}"
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    @Slot()
    def _update_auth_countdown(self):
        if self.remaining_auth_seconds > 0:
            self.remaining_auth_seconds -= 1
            is_reminder_time = self.remaining_auth_seconds <= 5 * 60
            self._update_auth_status_display(is_reminder_time)
        else:
            self.auth_countdown_timer.stop()
            self._handle_auth_expiration()

    def _handle_auth_expiration(self, initial_check=False, message=None):
        self.auth_countdown_timer.stop()
        self.periodic_check_timer.stop()
        display_message = message or "授权已到期或无效！"
        self.auth_status_label.setText(display_message)
        self.auth_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.append_log(display_message + " 请重新验证或订阅。")
        was_active = self.is_script_active
        if self.is_script_active:
            self.stop_script()
        self.enable_app_controls(False)
        if not was_active:
            self.script_stopped.emit()
        if not initial_check:
            QMessageBox.warning(self, "授权提醒", display_message + "\n您的功能已受限。")

    def enable_app_controls(self, enable: bool):
        self.start_button.setEnabled(enable)
        self.window_combo.setEnabled(enable)
        self.refresh_button.setEnabled(enable)
        self.key_input.setEnabled(enable)
        self.long_press_rb_yes.setEnabled(enable)
        self.long_press_rb_no.setEnabled(enable)
        self.interval_input.setEnabled(enable and not self.long_press_rb_yes.isChecked())
        if not enable:
            self.stop_button.setEnabled(False)

    @Slot()
    def _perform_periodic_status_check(self):
        self.append_log(f"[{time.strftime('%H:%M:%S')}] 定期检查授权状态...")
        worker = Worker(self.api.check_subscription_status)
        worker.signals.result.connect(self._handle_periodic_check_result)
        worker.signals.error.connect(self._handle_periodic_check_error)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_periodic_check_result(self, result):
        new_token_str, error = result
        if error or not new_token_str:
            self.append_log(f"定期状态检查API错误: {error or '未返回有效令牌'}")
            return
        try:
            secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.api.order_id))
            new_token_data = jwt.decode(new_token_str, secret_key, algorithms=["HS256"])
            self.append_log("授权状态已刷新。")
            self.auth_countdown_timer.stop()
            self.handle_authorization_status(new_token_data)
        except JWTError as e:
            self.append_log(f"刷新授权时令牌解析失败: {e}")
            self._handle_auth_expiration(message="授权信息刷新失败。")

    @Slot(str)
    def _handle_periodic_check_error(self, error_str: str):
        self.append_log(f"定期状态检查后台任务失败: {error_str}")

    @Slot()
    def start_script(self):
        if not self.start_button.isEnabled():
            self.append_log("无法启动：授权无效或功能被禁用。")
            return
        if self.is_script_active:
            self.append_log("脚本已在运行中。")
            return

        if not self.target_hwnd:
            QMessageBox.warning(self, "提示", "请先从下拉列表中选择一个目标窗口。")
            return

        key_to_press = self.key_input.text().strip()
        if len(key_to_press) != 1:
            QMessageBox.warning(self, "提示", "请输入单个目标按键。")
            return

        try:
            interval = float(self.interval_input.text())
            if not (0.1 <= interval <= 60.0):
                QMessageBox.warning(self, "输入错误", "间隔时间必须在 0.1 到 60 秒之间。")
                return
        except ValueError:
            QMessageBox.warning(self, "提示", "请输入有效的按键频率（秒）。")
            return

        long_press = self.long_press_rb_yes.isChecked()

        self.is_script_active = True
        self.enable_app_controls(False)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.app_status_label.setText("状态：运行中... (Alt+W 停止)")

        self.autokey_thread = AutoKeyThread(self.target_hwnd, key_to_press, interval, long_press)
        self.autokey_thread.log_message.connect(self.append_log)
        self.autokey_thread.finished.connect(self.on_script_finished)
        self.autokey_thread.start()

        self.script_started.emit()

    @Slot()
    def stop_script(self):
        if not self.is_script_active or not self.autokey_thread:
            return
        self.append_log("正在发送停止请求...")
        if self.autokey_thread.isRunning():
            self.autokey_thread.stop()

    @Slot()
    def on_script_finished(self):
        self.append_log("脚本线程已结束。")
        self.reset_ui_to_stopped_state()

    def reset_ui_to_stopped_state(self):
        was_active = self.is_script_active
        self.is_script_active = False
        is_auth_valid = self.remaining_auth_seconds > 0

        self.enable_app_controls(is_auth_valid)
        self.start_button.setEnabled(is_auth_valid)
        self.stop_button.setEnabled(False)

        self.autokey_thread = None
        self.app_status_label.setText("状态：已停止。按 Alt+Q 启动。")
        if was_active:
            self.script_stopped.emit()

    @Slot(str)
    def force_stop_script(self, message: str):
        self.append_log(f"强制停止脚本: {message}")
        if self.is_script_active and self.autokey_thread:
            self.autokey_thread.stop()
        else:
            self.reset_ui_to_stopped_state()
        QMessageBox.warning(self, "脚本已停止", message)
        self.auth_status_label.setText(message)
        self.auth_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.enable_app_controls(False)

    @Slot(str)
    def append_log(self, text: str):
        self.log_output.append(f"[{time.strftime('%H:%M:%S')}] {text}")

    def closeEvent(self, event):
        self.append_log("正在关闭应用程序...")
        self.auth_countdown_timer.stop()
        self.periodic_check_timer.stop()
        if self.autokey_thread and self.autokey_thread.isRunning():
            self.append_log("正在等待按键线程结束...")
            self.autokey_thread.stop()
            self.autokey_thread.wait(1000)
        if self.keyboard_hook and self.keyboard_hook.is_alive():
            self.append_log("正在停止热键监听...")
            self.keyboard_hook.stop()
        super().closeEvent(event)
