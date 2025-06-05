# client_qt/scripts/auto_click.py

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QProgressBar, QHBoxLayout, QLineEdit, QMessageBox
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QThread
from PySide6.QtGui import QIntValidator

from pynput import mouse, keyboard
import time
import datetime
from jose import jwt

from api_client import ApiClient  # 用于处理时间戳


class AutoClickerThread(QThread):
    """后台线程，用于执行自动点击逻辑，避免阻塞GUI。"""

    # status_update = Signal(str) # 状态更新将由主UI线程根据授权状态控制

    def __init__(self, interval_ms):
        super().__init__()
        self.interval_ms = interval_ms
        self._is_running = False
        self._mouse_controller = mouse.Controller()

    def run(self):
        self._is_running = True
        last_click_time = time.monotonic()
        while self._is_running:
            current_time = time.monotonic()
            if self.interval_ms > 0 and (current_time - last_click_time) * 1000 >= self.interval_ms:
                if not self._is_running:
                    break
                try:
                    self._mouse_controller.click(mouse.Button.left, 1)
                    last_click_time = current_time
                except Exception as e:
                    print(f"AutoClickerThread Click Error: {e}")

            time.sleep(self.interval_ms)
        self._is_running = False

    def stop(self):
        self._is_running = False


class MainAppPage(QWidget):
    """主应用页面，集成试用/订阅倒计时和自动点击功能。"""

    authorization_required = Signal()
    script_started = Signal()  # 新增：脚本成功启动时发出
    script_stopped = Signal()  # 新增：脚本停止时发出

    PERIODIC_CHECK_INTERVAL_MS = 3 * 1000

    def __init__(self, email: str, api_client_instance: ApiClient, initial_auth_token_data: dict, thread_pool_instance):
        super().__init__()

        self.user_email = email
        self.api = api_client_instance
        self.thread_pool = thread_pool_instance

        self.auto_clicker_thread = None
        self.is_clicking_active = False
        self.keyboard_hook = None

        self.auth_countdown_timer = QTimer(self)
        self.auth_countdown_timer.timeout.connect(self._update_auth_countdown)

        self.periodic_check_timer = QTimer(self)
        self.periodic_check_timer.timeout.connect(self._perform_periodic_status_check)

        self.current_expire_time_dt = None
        self.remaining_auth_seconds = 0

        self._init_ui()
        self._setup_global_hotkeys()
        # self.handle_authorization_status(initial_auth_token_data)

    def _init_ui(self):
        layout = QVBoxLayout(self)

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

        auto_click_layout = QHBoxLayout()
        interval_label = QLabel("点击间隔 (秒):")
        self.interval_input = QLineEdit("1")
        self.interval_input.setValidator(QIntValidator(1, 600))
        self.interval_input.setFixedWidth(80)

        self.start_button = QPushButton("启动 (Alt+Q)")
        self.stop_button = QPushButton("停止 (Alt+W)")
        self.stop_button.setEnabled(False)

        auto_click_layout.addWidget(interval_label)
        auto_click_layout.addWidget(self.interval_input)
        auto_click_layout.addStretch()
        auto_click_layout.addWidget(self.start_button)
        auto_click_layout.addWidget(self.stop_button)

        self.app_status_label = QLabel("状态：已停止。按 Alt+Q 启动。")
        self.app_status_label.setAlignment(Qt.AlignCenter)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.append("自动点击器准备就绪。")

        layout.addWidget(self.welcome_label)
        layout.addWidget(self.auth_status_label)
        layout.addLayout(auto_click_layout)
        layout.addWidget(self.app_status_label)
        layout.addWidget(self.log_output)

        self.start_button.clicked.connect(self.start_auto_clicker)
        self.stop_button.clicked.connect(self.stop_auto_clicker)

    def handle_authorization_status(self, token_data: dict):
        if not token_data:
            self._handle_auth_expiration(message="无法获取授权信息，请重新登录。")
            return

        expire_time_str = datetime.datetime.fromtimestamp(token_data.get('expire_time'))
        rest_time_delta_str = token_data.get('rest_time')
        reminder = token_data.get('reminder', False)

        if not expire_time_str or rest_time_delta_str is None:
            self._handle_auth_expiration(message="授权信息不完整，请重新登录。")
            return

        try:
            self.current_expire_time_dt = expire_time_str

            if isinstance(rest_time_delta_str, (int, float)):
                self.remaining_auth_seconds = int(rest_time_delta_str)
            elif isinstance(rest_time_delta_str, str):
                parts = rest_time_delta_str.split(', ')
                time_part = parts[-1]
                h, m, s_float = map(float, time_part.split(':'))  # s_float might have milliseconds
                s = int(s_float)  # Convert to int, truncating milliseconds
                total_seconds = h * 3600 + m * 60 + s
                if len(parts) > 1 and "day" in parts[0]:
                    days = int(parts[0].split(' ')[0])
                    total_seconds += days * 86400
                self.remaining_auth_seconds = int(total_seconds)
            else:
                self.remaining_auth_seconds = int(rest_time_delta_str.total_seconds())

        except Exception as e:
            self.log_output.append(f"解析时间时出错: {e}")
            self._handle_auth_expiration(message="授权时间信息格式错误。")
            return

        if self.remaining_auth_seconds <= 0:
            self._handle_auth_expiration(initial_check=True)
        else:
            self.auth_countdown_timer.start(1000)
            self.periodic_check_timer.start(self.PERIODIC_CHECK_INTERVAL_MS)
            self._update_auth_status_display(reminder)
            self.enable_app_controls(True)
            self.log_output.append(f"授权有效，剩余时间约 {self._format_time(self.remaining_auth_seconds)}。")
            if reminder:
                self.log_output.append("[黄色]提醒：您的授权即将到期！[/黄色]")

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
        self.log_output.append(display_message + " 请重新验证或订阅。")

        was_clicking = self.is_clicking_active
        self.enable_app_controls(False)  # 这会调用 stop_auto_clicker if active

        if was_clicking and not self.is_clicking_active:  # 确保如果之前在运行，现在确实停了
            pass  # script_stopped 会在 stop_auto_clicker 或 on_clicker_thread_finished 中发出
        elif not was_clicking:  # 如果本来就没在运行，但授权过期了
            self.script_stopped.emit()  # 也通知一下，确保心跳停止

        if not initial_check:
            QMessageBox.warning(self, "授权提醒", display_message + "\n您的功能已受限。")
        self.authorization_required.emit()

    def enable_app_controls(self, enable: bool):
        self.start_button.setEnabled(enable)
        self.interval_input.setEnabled(enable)
        if not enable:
            self.stop_button.setEnabled(False)
            if self.is_clicking_active:
                self.stop_auto_clicker()

    @Slot()
    def _perform_periodic_status_check(self):
        if not self.api or not hasattr(self.api, 'check_subscription_status'):
            self.log_output.append("错误：API客户端未初始化或缺少检查方法，无法执行定期状态检查。")
            self.periodic_check_timer.stop()
            return

        self.log_output.append(f"[{time.strftime('%H:%M:%S')}] 定期检查授权状态...")

        if not self.thread_pool:
            self.log_output.append("错误: QThreadPool 未初始化，无法后台执行状态检查。")
            return

        from worker import Worker

        worker = Worker(lambda: self.api.check_subscription_status())
        worker.signals.result.connect(self._handle_periodic_check_result)
        worker.signals.error.connect(self._handle_periodic_check_error)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_periodic_check_result(self, result):
        new_token_str, error = result  # new_token_data 是解码前的字典
        secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.api.order_id, self.user_email))
        new_token_data = jwt.decode(new_token_str, secret_key, algorithms=["HS256"])
        if error:
            self.log_output.append(f"定期状态检查API错误: {error}")
            return

        if new_token_data:
            self.log_output.append("授权状态已刷新。")
            self.auth_countdown_timer.stop()  # 先停止旧的计时器
            self.handle_authorization_status(new_token_data)  # 使用新的令牌数据更新
        else:
            self.log_output.append("定期状态检查未返回有效令牌数据。")
            self._handle_auth_expiration(message="授权信息刷新失败。")

    @Slot(str)
    def _handle_periodic_check_error(self, error_str: str):
        self.log_output.append(f"定期状态检查后台任务失败: {error_str}")

    def _setup_global_hotkeys(self):
        self.pressed_keys = set()

        def on_press(key):
            try:
                # Normalize alt keys
                current_alt_keys = {keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}
                if key in current_alt_keys:
                    self.pressed_keys.add(keyboard.Key.alt)  # Use a generic alt representation

                if hasattr(key, 'char') and key.char:
                    char_lower = key.char.lower()
                    if char_lower == 'q' and keyboard.Key.alt in self.pressed_keys:
                        if not self.is_clicking_active and self.start_button.isEnabled():
                            QTimer.singleShot(0, self.start_auto_clicker)  # Schedule to run in main thread
                    elif char_lower == 'w' and keyboard.Key.alt in self.pressed_keys:
                        if self.is_clicking_active and self.stop_button.isEnabled():
                            QTimer.singleShot(0, self.stop_auto_clicker)  # Schedule to run in main thread
            except Exception as e:
                print(f"Hotkey press error: {e}")

        def on_release(key):
            try:
                current_alt_keys = {keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}
                if key in current_alt_keys:
                    if keyboard.Key.alt in self.pressed_keys:  # Check before removing
                        self.pressed_keys.remove(keyboard.Key.alt)
            except Exception as e:  # Catch specific error if possible, e.g. KeyError
                print(f"Hotkey release error: {e}")

        try:
            self.keyboard_hook = keyboard.Listener(on_press=on_press, on_release=on_release, suppress=False)
            self.keyboard_hook.start()
            self.log_output.append("全局热键 Alt+Q (启动) 和 Alt+W (停止) 已尝试激活。")
        except Exception as e:
            self.log_output.append(f"[错误] 无法启动全局热键监听: {e}")
            # QMessageBox.warning(self, "热键警告", f"无法启动全局热键监听器：{e}\n请使用界面按钮。")
            self.keyboard_hook = None  # Ensure it's None if failed

    @Slot()
    def start_auto_clicker(self):
        self.script_started.emit()  # <-- 发出脚本启动信号
        if not self.start_button.isEnabled():
            self.log_output.append("无法启动：授权无效或功能被禁用。")
            return
        if self.is_clicking_active:
            self.log_output.append("自动点击已在运行中。")
            return
        try:
            interval = int(self.interval_input.text())
            if not (1 <= interval <= 600):
                QMessageBox.warning(self, "输入错误", "间隔时间必须在 1 到 600 秒之间。")
                return
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字作为间隔时间。")
            return

        self.is_clicking_active = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.interval_input.setEnabled(False)

        self.auto_clicker_thread = AutoClickerThread(interval)
        self.auto_clicker_thread.finished.connect(self.on_clicker_thread_finished)
        self.auto_clicker_thread.start()
        self.update_app_status_label(f"运行中... 间隔: {interval/1000.0:.2f} 秒. (Alt+W 停止)")
        self.log_output.append(f"自动点击已启动，间隔 {interval/1000.0:.2f} 秒。")

    @Slot()
    def stop_auto_clicker(self):
        if not self.is_clicking_active or not self.auto_clicker_thread:
            self.reset_ui_to_stopped_state()  # Ensure UI is correct even if called redundantly
            # self.script_stopped.emit() # Emit if called when already stopped, to ensure heartbeat stops.
            return

        self.log_output.append("正在发送停止请求...")
        if self.auto_clicker_thread:
            self.auto_clicker_thread.stop()
        # actual emit of script_stopped will happen in on_clicker_thread_finished
        # or reset_ui_to_stopped_state if already stopped.

    @Slot(str)
    def update_app_status_label(self, text: str):
        self.app_status_label.setText(f"点击器状态：{text}")

    @Slot()
    def on_clicker_thread_finished(self):
        self.reset_ui_to_stopped_state()  # This will emit script_stopped

    def reset_ui_to_stopped_state(self):
        is_auth_valid = self.remaining_auth_seconds > 0

        # Only change state if it was active, to prevent multiple signals if already stopped.
        was_active = self.is_clicking_active
        self.is_clicking_active = False

        self.start_button.setEnabled(is_auth_valid)  # Start button state depends on auth
        self.interval_input.setEnabled(is_auth_valid)
        self.stop_button.setEnabled(False)  # Stop button always disabled when not running

        if self.auto_clicker_thread and not self.auto_clicker_thread.isRunning():
            self.auto_clicker_thread = None

        self.update_app_status_label("已停止。按 Alt+Q 启动。")
        if was_active:  # Only emit if it was truly active and is now stopping
            self.script_stopped.emit()  # <-- 发出脚本停止信号

    # 新增：强制停止脚本的方法
    @Slot(str)
    def force_stop_script(self, message: str):
        """
        由外部（如MainWindow的心跳）调用以强制停止脚本。
        """
        self.log_output.append(f"强制停止脚本: {message}")
        if self.is_clicking_active:
            if self.auto_clicker_thread:
                self.auto_clicker_thread.stop()  # Request thread to stop
            # The on_clicker_thread_finished will call reset_ui_to_stopped_state, which emits script_stopped
            # If thread is already somehow gone, ensure UI reset and signal.
            if not self.auto_clicker_thread or not self.auto_clicker_thread.isRunning():
                self.reset_ui_to_stopped_state()
        else:
            # If not active, ensure UI is in stopped state and signal is emitted if it wasn't
            self.reset_ui_to_stopped_state()

        QMessageBox.warning(self, "脚本已停止", message)
        # Potentially disable more UI elements or guide user
        self.auth_status_label.setText(message)
        self.auth_status_label.setStyleSheet("color: red; font-weight: bold;")
        self.enable_app_controls(False)  # Ensure main controls are disabled

    def append_log(self, text: str):
        self.log_output.append(text)

    def closeEvent(self, event):
        self.log_output.append("正在关闭应用程序...")
        if self.is_clicking_active and self.auto_clicker_thread:
            self.log_output.append("停止自动点击线程...")
            self.auto_clicker_thread.stop()
            if not self.auto_clicker_thread.wait(500):
                self.log_output.append("自动点击线程未能及时停止。")

        if self.keyboard_hook:
            self.log_output.append("停止键盘监听器...")
            try:
                self.keyboard_hook.stop()
                self.keyboard_hook.join(timeout=0.5)  # Attempt to join listener thread
            except Exception as e:
                print(f"停止键盘监听器时出错: {e}")

        self.auth_countdown_timer.stop()
        self.periodic_check_timer.stop()
        super().closeEvent(event)
