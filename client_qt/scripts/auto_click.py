# widgets/main_app_page.py

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QTextEdit,
                               QPushButton, QProgressBar, QHBoxLayout, QLineEdit,
                               QMessageBox)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QThread
from PySide6.QtGui import QIntValidator

# 用于鼠标控制和键盘监听
from pynput import mouse, keyboard
import time
import datetime

from api_client import ApiClient # 用于处理时间戳

# 假设 api_client.py 和 worker.py 在可导入路径
# from api_client import ApiClient # MainWindow会传入实例
# from worker import Worker # MainWindow会传入实例的 thread_pool

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
            # 确保 interval_ms > 0 避免除零错误
            if self.interval_ms > 0 and (current_time - last_click_time) * 1000 >= self.interval_ms:
                if not self._is_running: # 双重检查
                    break
                try:
                    self._mouse_controller.click(mouse.Button.left, 1)
                    last_click_time = current_time
                except Exception as e:
                    print(f"AutoClickerThread Click Error: {e}") # 应该通过信号报告错误
            
            # 动态调整休眠时间，更及时地响应停止信号
            time.sleep(min(0.01, self.interval_ms / 2000.0 if self.interval_ms > 0 else 0.01))
        self._is_running = False

    def stop(self):
        self._is_running = False


class MainAppPage(QWidget):
    """主应用页面，集成试用/订阅倒计时和自动点击功能。"""
    authorization_required = Signal() # 当授权到期或需要用户操作时发出

    # 定期检查授权状态的间隔（例如：4分钟，略小于5分钟的典型最短过期时间）
    PERIODIC_CHECK_INTERVAL_MS = 4 * 60 * 1000

    def __init__(self, email: str, api_client_instance:ApiClient, initial_auth_token_data: dict, thread_pool_instance):
        super().__init__()
        
        self.user_email = email
        self.api = api_client_instance
        self.thread_pool = thread_pool_instance # 从 MainWindow 传入 QThreadPool

        self.auto_clicker_thread = None
        self.is_clicking_active = False
        self.keyboard_hook = None

        # 统一的授权倒计时器
        self.auth_countdown_timer = QTimer(self)
        self.auth_countdown_timer.timeout.connect(self._update_auth_countdown)
        
        # 定期状态检查计时器
        self.periodic_check_timer = QTimer(self)
        self.periodic_check_timer.timeout.connect(self._perform_periodic_status_check)

        self.current_expire_time_dt = None
        self.remaining_auth_seconds = 0

        self._init_ui()
        self._setup_global_hotkeys()
        self.handle_authorization_status(initial_auth_token_data) # 使用初始令牌数据

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        self.welcome_label = QLabel(f"授权成功！欢迎您，{self.user_email}")
        font = self.welcome_label.font()
        font.setPointSize(16); self.welcome_label.setFont(font)
        self.welcome_label.setAlignment(Qt.AlignCenter)

        self.auth_status_label = QLabel("授权状态：正在初始化...")
        self.auth_status_label.setAlignment(Qt.AlignCenter)
        font_status = self.auth_status_label.font(); font_status.setPointSize(10); self.auth_status_label.setFont(font_status)

        auto_click_layout = QHBoxLayout()
        interval_label = QLabel("点击间隔 (毫秒):")
        self.interval_input = QLineEdit("1000")
        self.interval_input.setValidator(QIntValidator(100, 600000))
        self.interval_input.setFixedWidth(80)
        
        self.start_button = QPushButton("启动 (Alt+Q)")
        self.stop_button = QPushButton("停止 (Alt+W)")
        self.stop_button.setEnabled(False)

        auto_click_layout.addWidget(interval_label); auto_click_layout.addWidget(self.interval_input)
        auto_click_layout.addStretch(); auto_click_layout.addWidget(self.start_button)
        auto_click_layout.addWidget(self.stop_button)
        
        self.app_status_label = QLabel("状态：已停止。按 Alt+Q 启动。")
        self.app_status_label.setAlignment(Qt.AlignCenter)
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True); self.log_output.append("自动点击器准备就绪。")
        
        layout.addWidget(self.welcome_label); layout.addWidget(self.auth_status_label)
        layout.addLayout(auto_click_layout); layout.addWidget(self.app_status_label)
        layout.addWidget(self.log_output)
        
        self.start_button.clicked.connect(self.start_auto_clicker)
        self.stop_button.clicked.connect(self.stop_auto_clicker)

    def handle_authorization_status(self, token_data: dict):
        """根据传入的解码后令牌数据，更新授权状态和UI。"""
        if not token_data:
            self._handle_auth_expiration(message="无法获取授权信息，请重新登录。")
            return

        expire_time_str = token_data.get('expire_time') # 假设是 ISO 格式字符串或时间戳
        rest_time_delta_str = token_data.get('rest_time') # 假设是 "days, H:M:S.ms" 或总秒数
        reminder = token_data.get('reminder', False)

        if not expire_time_str or rest_time_delta_str is None: # rest_time 可以是0
            self._handle_auth_expiration(message="授权信息不完整，请重新登录。")
            return
        
        try:
            # 解析 expire_time (假设是ISO格式的UTC时间字符串)
            # 如果是时间戳，则 datetime.datetime.fromtimestamp(expire_time_str, tz=datetime.timezone.utc)
            self.current_expire_time_dt = datetime.datetime.fromisoformat(expire_time_str.replace("Z", "+00:00"))
            
            # 解析 rest_time ( timedelta 字符串如 "1 day, 1:23:45" 或纯秒数)
            # 您的后端返回的是 timedelta 对象，它在JSON中通常会序列化为字符串或总秒数
            # 这里我们假设后端已将其转换为总秒数 (int or float)
            if isinstance(rest_time_delta_str, (int, float)):
                 self.remaining_auth_seconds = int(rest_time_delta_str)
            elif isinstance(rest_time_delta_str, str): # 尝试解析 "H:M:S" 或 "D days, H:M:S"
                # 这是一个简化的解析，对于复杂的timedelta字符串需要更健壮的解析器
                parts = rest_time_delta_str.split(', ')
                time_part = parts[-1]
                h, m, s = map(float, time_part.split(':'))
                total_seconds = h * 3600 + m * 60 + s
                if len(parts) > 1 and "day" in parts[0]:
                    days = int(parts[0].split(' ')[0])
                    total_seconds += days * 86400
                self.remaining_auth_seconds = int(total_seconds)
            else: # 如果是 timedelta 对象 (不太可能直接从JSON获得)
                 self.remaining_auth_seconds = int(rest_time_delta_str.total_seconds())

        except Exception as e:
            self.log_output.append(f"解析时间时出错: {e}")
            self._handle_auth_expiration(message="授权时间信息格式错误。")
            return

        if self.remaining_auth_seconds <= 0:
            self._handle_auth_expiration(initial_check=True)
        else:
            self.auth_countdown_timer.start(1000) # 每秒更新一次
            self.periodic_check_timer.start(self.PERIODIC_CHECK_INTERVAL_MS) # 启动定期检查
            self._update_auth_status_display(reminder)
            self.enable_app_controls(True)
            self.log_output.append(f"授权有效，剩余时间约 {self._format_time(self.remaining_auth_seconds)}。")
            if reminder:
                self.log_output.append("[黄色]提醒：您的授权即将到期！[/黄色]") # 假设log支持rich格式

    def _update_auth_status_display(self, reminder: bool):
        """更新授权状态标签的显示内容"""
        time_str = self._format_time(self.remaining_auth_seconds)
        expire_date_str = self.current_expire_time_dt.strftime('%Y-%m-%d %H:%M:%S') if self.current_expire_time_dt else "N/A"
        
        status_text = f"剩余时间: {time_str} (有效期至: {expire_date_str})"
        if reminder:
            status_text = f"[!] 即将到期！{status_text}"
            self.auth_status_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.auth_status_label.setStyleSheet("color: green;") # 正常状态
        self.auth_status_label.setText(status_text)


    def _format_time(self, seconds):
        seconds = max(0, int(seconds)) #确保是非负整数
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    @Slot()
    def _update_auth_countdown(self):
        if self.remaining_auth_seconds > 0:
            self.remaining_auth_seconds -= 1
            # 检查是否需要触发提醒状态 (虽然后端也会给，但客户端也可以动态判断)
            is_reminder_time = (self.remaining_auth_seconds <= 5 * 60) # 假设5分钟提醒
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
        self.enable_app_controls(False)
        if self.is_clicking_active:
            self.stop_auto_clicker()
        
        if not initial_check:
            QMessageBox.warning(self, "授权提醒", display_message + "\n您的功能已受限。")
        self.authorization_required.emit()

    def enable_app_controls(self, enable: bool):
        self.start_button.setEnabled(enable)
        self.interval_input.setEnabled(enable)
        if not enable: # 如果整体禁用，则停止按钮也应禁用，自动点击逻辑会处理
            self.stop_button.setEnabled(False)
            if self.is_clicking_active: #如果因为授权问题禁用控件，确保点击器也停了
                self.stop_auto_clicker()

    @Slot()
    def _perform_periodic_status_check(self):
        if not self.api or not hasattr(self.api, 'check_subscription_status'):
            self.log_output.append("错误：API客户端未初始化或缺少检查方法，无法执行定期状态检查。")
            self.periodic_check_timer.stop() # 避免无限循环错误日志
            return

        self.log_output.append(f"[{time.strftime('%H:%M:%S')}] 定期检查授权状态...")
        
        # 需要从 MainWindow 获取 QThreadPool 实例来运行后台任务
        if not self.thread_pool:
            self.log_output.append("错误: QThreadPool 未初始化，无法后台执行状态检查。")
            return
            
        from worker import Worker # 确保 Worker 可用
        worker = Worker(lambda: self.api.check_subscription_status(self.api.order_id))
        worker.signals.result.connect(self._handle_periodic_check_result)
        worker.signals.error.connect(self._handle_periodic_check_error)
        self.thread_pool.start(worker)

    @Slot(object)
    def _handle_periodic_check_result(self, result):
        # result 应该是 (decoded_token_dict, None)
        new_token_data, error = result
        if error:
            self.log_output.append(f"定期状态检查API错误: {error}")
            # 根据策略，可以允许一段时间的离线使用，或者立即标记为过期
            # self._handle_auth_expiration(message="无法连接服务器更新授权，功能可能受限。")
            # 暂时不改变状态，等待下次成功或明确过期
            return

        if new_token_data:
            self.log_output.append("授权状态已刷新。")
            # 使用新的令牌数据更新整个授权状态
            # 在调用 handle_authorization_status 前停止旧的计时器很重要
            self.auth_countdown_timer.stop()
            self.handle_authorization_status(new_token_data)
        else:
            self.log_output.append("定期状态检查未返回有效令牌数据。")
            # 可能需要处理这种情况，例如认为授权丢失
            self._handle_auth_expiration(message="授权信息刷新失败。")


    @Slot(str)
    def _handle_periodic_check_error(self, error_str: str):
        self.log_output.append(f"定期状态检查后台任务失败: {error_str}")
        # 同样，可以根据策略决定是否立即禁用

    def _setup_global_hotkeys(self):
        # ... (热键设置代码保持不变) ...
        self.pressed_keys = set()
        def on_press(key):
            try:
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
                    self.pressed_keys.add(keyboard.Key.alt)
                elif hasattr(key, 'char') and key.char:
                    if key.char.lower() == 'q' and keyboard.Key.alt in self.pressed_keys:
                        if not self.is_clicking_active and self.start_button.isEnabled():
                            self.start_auto_clicker()
                    elif key.char.lower() == 'w' and keyboard.Key.alt in self.pressed_keys:
                        if self.is_clicking_active and self.stop_button.isEnabled():
                            self.stop_auto_clicker()
            except Exception as e:
                print(f"Hotkey press error: {e}") 
        def on_release(key):
            try:
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr):
                    if keyboard.Key.alt in self.pressed_keys:
                        self.pressed_keys.remove(keyboard.Key.alt)
            except Exception as e:
                print(f"Hotkey release error: {e}")
        try:
            self.keyboard_hook = keyboard.Listener(on_press=on_press, on_release=on_release, suppress=False)
            self.keyboard_hook.start()
            self.log_output.append("全局热键 Alt+Q (启动) 和 Alt+W (停止) 已尝试激活。")
        except Exception as e:
            self.log_output.append(f"[错误] 无法启动全局热键监听: {e}")
            QMessageBox.warning(self, "热键警告", f"无法启动全局热键监听器：{e}\n请使用界面按钮。")
            self.keyboard_hook = None


    @Slot()
    def start_auto_clicker(self):
        if not self.start_button.isEnabled(): 
            self.log_output.append("无法启动：授权无效或功能被禁用。")
            return
        if self.is_clicking_active:
            self.log_output.append("自动点击已在运行中。")
            return
        try:
            interval = int(self.interval_input.text())
            if not (100 <= interval <= 600000):
                QMessageBox.warning(self, "输入错误", "间隔时间必须在 100 到 600000 毫秒之间。")
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
            # self.log_output.append("自动点击未运行。") # 可能会在授权过期时重复触发
            self.reset_ui_to_stopped_state()
            return
        
        self.log_output.append("正在发送停止请求...")
        if self.auto_clicker_thread:
            self.auto_clicker_thread.stop()


    @Slot(str)
    def update_app_status_label(self, text: str): 
        self.app_status_label.setText(f"点击器状态：{text}")
    
    @Slot()
    def on_clicker_thread_finished(self):
        # self.log_output.append("自动点击线程已结束。") # 可能会显得多余
        self.reset_ui_to_stopped_state()

    def reset_ui_to_stopped_state(self):
        self.is_clicking_active = False
        
        # 检查授权状态来决定是否启用开始按钮
        is_auth_valid = self.remaining_auth_seconds > 0
        self.start_button.setEnabled(is_auth_valid)
        self.interval_input.setEnabled(is_auth_valid)
            
        self.stop_button.setEnabled(False)
        
        if self.auto_clicker_thread and not self.auto_clicker_thread.isRunning():
            self.auto_clicker_thread = None
        
        self.update_app_status_label("已停止。按 Alt+Q 启动。")

    def append_log(self, text: str):
        self.log_output.append(text)

    def closeEvent(self, event):
        # ... (此方法逻辑基本不变，确保停止所有计时器和线程) ...
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
            except Exception as e:
                print(f"停止键盘监听器时出错: {e}")
        
        self.auth_countdown_timer.stop()
        self.periodic_check_timer.stop()
        super().closeEvent(event)

