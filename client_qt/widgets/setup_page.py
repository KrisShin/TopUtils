# widgets/setup_page.py

import qrcode
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QStackedWidget, QMessageBox, QFormLayout
from PySide6.QtCore import Qt, Signal, Slot

from widgets.utils import pil_to_qpixmap


class SetupPage(QWidget):
    """
    引导新用户完成设置的页面。
    包含两个步骤：1. 输入邮箱；2. 设置并确认TOTP。
    """

    # 定义信号，用于通知主窗口用户的操作
    # Signal(str) -> 发送用户输入的邮箱
    email_submitted = Signal(str)
    # Signal(str) -> 发送用户输入的TOTP码以完成绑定
    totp_confirmed = Signal(str)

    def __init__(self):
        super().__init__()

        # 主布局和页面切换器
        main_layout = QVBoxLayout(self)
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        # 创建两个步骤的页面
        self.email_page = self._create_email_page()
        self.totp_page = self._create_totp_page()

        # 添加到页面切换器
        self.stacked_widget.addWidget(self.email_page)
        self.stacked_widget.addWidget(self.totp_page)

    def _create_email_page(self):
        """创建第一步：输入邮箱的界面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        info_label = QLabel("欢迎！请输入您的邮箱以绑定授权。")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your.email@example.com")
        self.next_button = QPushButton("下一步")
         # 绑定回车信号到按钮点击
        self.next_button.clicked.connect(self._on_email_submit)
        self.email_input.returnPressed.connect(self.next_button.click)

        layout.addWidget(info_label)
        layout.addWidget(self.email_input)
        layout.addWidget(self.next_button)
        return page

    def _create_totp_page(self):
        """创建第二步：设置TOTP的界面"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        info_label = QLabel("请使用微信搜索[腾讯身份验证器]小程序选择[二维码激活]扫描下方的二维码：")
        self.qr_label = QLabel()
        self.qr_label.setFixedSize(250, 250)
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")

        form_layout = QFormLayout()
        self.totp_input = QLineEdit()
        self.totp_input.setPlaceholderText("6位数字码")
        self.confirm_button = QPushButton("完成绑定")

        self.confirm_button.clicked.connect(self._on_totp_confirm)

        form_layout.addRow("验证码:", self.totp_input)

        layout.addWidget(info_label)
        layout.addWidget(self.qr_label)
        layout.addLayout(form_layout)
        layout.addWidget(self.confirm_button)
        return page

    def show_email_step(self):
        """公开方法：切换到输入邮箱的步骤"""
        self.stacked_widget.setCurrentWidget(self.email_page)

    def show_totp_step(self, uri: str):
        """公开方法：接收URI，生成并显示二维码，然后切换到TOTP步骤"""
        try:
            # 使用qrcode库从URI生成PIL Image对象
            qr_image = qrcode.make(uri)
            pixmap = pil_to_qpixmap(qr_image)
            self.qr_label.setPixmap(pixmap.scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.stacked_widget.setCurrentWidget(self.totp_page)
        except Exception as e:
            from traceback import print_exc

            print_exc()
            QMessageBox.critical(self, "错误", f"生成二维码失败: {e}")

    @Slot()
    def _on_email_submit(self):
        email = self.email_input.text().strip()
        if not email or '@' not in email or '.' not in email.split('@')[-1]:
            # 简单的邮箱格式验证
            QMessageBox.warning(self, "提示", "请输入有效的邮箱地址。")
            self.reset_buttons()
            return
        self.next_button.setEnabled(False)
        self.next_button.setText("处理中...")
        self.email_submitted.emit(email)

    @Slot()
    def _on_totp_confirm(self):
        code = self.totp_input.text().strip()
        if len(code) != 6 or not code.isdigit():
            QMessageBox.warning(self, "提示", "请输入6位数字验证码。")
            return
        self.confirm_button.setEnabled(False)
        self.confirm_button.setText("验证中...")
        self.totp_confirmed.emit(code)

    def reset_buttons(self):
        """重置按钮状态，以便在出错后用户可以重试"""
        self.next_button.setEnabled(True)
        self.next_button.setText("下一步")
        self.confirm_button.setEnabled(True)
        self.confirm_button.setText("完成绑定")
