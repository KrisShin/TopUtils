# widgets/login_page.py

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget, QFormLayout, QHBoxLayout, QMessageBox
from PySide6.QtCore import Qt, Signal, Slot, QTimer  # 导入 QTimer


class LoginPage(QWidget):
    """
    用户登录页面，支持TOTP和邮箱两种验证方式。
    """

    login_requested = Signal(str, str)
    email_code_requested = Signal()

    # 倒计时秒数
    COUNTDOWN_SECONDS = 60

    def __init__(self, email: str):
        super().__init__()
        self.user_email = email
        self.countdown_timer = QTimer(self)  # 初始化计时器
        self.remaining_seconds = 0

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)

        self.welcome_label = QLabel(f"你好, {self.user_email}")
        font = self.welcome_label.font()
        font.setPointSize(14)
        self.welcome_label.setFont(font)

        self.tab_widget = QTabWidget()
        self.totp_tab = self._create_totp_tab()
        self.email_tab = self._create_email_tab()

        self.tab_widget.addTab(self.totp_tab, "身份验证器")
        self.tab_widget.addTab(self.email_tab, "邮箱验证码")

        main_layout.addWidget(self.welcome_label, alignment=Qt.AlignCenter)
        main_layout.addWidget(self.tab_widget)

        # 连接计时器信号
        self.countdown_timer.timeout.connect(self._update_countdown)

    def _create_totp_tab(self):
        page = QWidget()
        layout = QFormLayout(page)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self.totp_input = QLineEdit()
        self.totp_input.setPlaceholderText("请输入6位动态码")
        self.totp_login_button = QPushButton("登录")

        layout.addRow("动态码:", self.totp_input)
        layout.addRow(self.totp_login_button)
        self.totp_login_button.clicked.connect(self._on_totp_login_request)
        self.totp_input.returnPressed.connect(self.totp_login_button.click)
        return page

    def _create_email_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        h_layout = QHBoxLayout()
        self.email_code_input = QLineEdit()
        self.email_code_input.setPlaceholderText("请输入邮箱收到的验证码")
        self.send_code_button = QPushButton("发送验证码")
        h_layout.addWidget(self.email_code_input)
        h_layout.addWidget(self.send_code_button)

        self.email_login_button = QPushButton("登录")

        layout.addLayout(h_layout)
        layout.addWidget(self.email_login_button)

        self.send_code_button.clicked.connect(self._on_send_email_code_request)
        self.email_login_button.clicked.connect(self._on_email_login_request)
        self.email_code_input.returnPressed.connect(self.email_login_button.click)

        return page

    @Slot()
    def _on_totp_login_request(self):
        code = self.totp_input.text().strip()
        if not code or len(code) != 6:
            QMessageBox.warning(self, "提示", "请输入6位动态码。")
            return
        self.login_requested.emit("1", code)  # "1" 代表TOTP方式

    @Slot()
    def _on_email_login_request(self):
        code = self.email_code_input.text().strip()
        if not code or len(code) != 6:
            QMessageBox.warning(self, "提示", "请输入正确格式的邮箱验证码。")
            return
        self.login_requested.emit("2", code)  # "2" 代表邮箱验证码方式

    @Slot()
    def _on_send_email_code_request(self):
        self.send_code_button.setEnabled(False)  # 先禁用，等待MainWindow反馈
        self.send_code_button.setText("发送中...")
        self.email_code_requested.emit()

    def on_login_start(self):
        self.totp_login_button.setEnabled(False)
        self.email_login_button.setEnabled(False)
        self.totp_login_button.setText("登录中...")
        self.email_login_button.setText("登录中...")

    def reset_login_buttons(self):
        self.totp_login_button.setEnabled(True)
        self.email_login_button.setEnabled(True)
        self.totp_login_button.setText("登录")
        self.email_login_button.setText("登录")

    @Slot(bool, str)
    def on_email_code_sent(self, success: bool, message: str):
        """处理发送邮箱验证码后的反馈，并启动倒计时"""
        if success:
            self.send_code_button.setText(message)  # 例如 "已发送"
            self.start_countdown()
        else:
            self.send_code_button.setText(message)  # 例如 "发送失败"
            self.send_code_button.setEnabled(True)  # 允许重试

    def start_countdown(self):
        """开始发送验证码按钮的倒计时"""
        self.remaining_seconds = self.COUNTDOWN_SECONDS
        self.send_code_button.setEnabled(False)  # 倒计时期间禁用
        self._update_countdown_text()
        self.countdown_timer.start(1000)  # 每1000毫秒（1秒）触发一次timeout信号

    @Slot()
    def _update_countdown(self):
        """计时器每秒调用的槽函数"""
        self.remaining_seconds -= 1
        if self.remaining_seconds > 0:
            self._update_countdown_text()
        else:
            self.countdown_timer.stop()
            self.send_code_button.setText("重新发送")
            self.send_code_button.setEnabled(True)

    def _update_countdown_text(self):
        """更新按钮上的倒计时文本"""
        self.send_code_button.setText(f"{self.remaining_seconds}秒后重发")
