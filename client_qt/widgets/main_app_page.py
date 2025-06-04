# widgets/main_app_page.py

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QPushButton, QProgressBar
from PySide6.QtCore import Qt, Signal, Slot

class MainAppPage(QWidget):
    """
    主应用页面，在用户成功登录后显示。
    """
    # 定义信号，当用户点击“开始”按钮时发出
    task_requested = Signal()

    def __init__(self, email: str):
        super().__init__()
        
        layout = QVBoxLayout(self)
        
        self.welcome_label = QLabel(f"授权成功！欢迎您，{email}")
        font = self.welcome_label.font()
        font.setPointSize(16)
        self.welcome_label.setFont(font)
        self.welcome_label.setAlignment(Qt.AlignCenter)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.append("系统准备就绪，可以开始执行任务。")

        self.start_task_button = QPushButton("开始执行任务")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False) # 默认隐藏

        layout.addWidget(self.welcome_label)
        layout.addWidget(self.log_output)
        layout.addWidget(self.start_task_button)
        layout.addWidget(self.progress_bar)
        
        self.start_task_button.clicked.connect(self._on_task_start)
        
    @Slot()
    def _on_task_start(self):
        """点击按钮时，禁用按钮并显示进度条，然后发出信号"""
        self.start_task_button.setEnabled(False)
        self.start_task_button.setText("任务执行中...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0) # 设置为不确定模式（滚动条动画）
        self.log_output.append("\n开始执行一项耗时任务...")
        self.task_requested.emit()

    @Slot(str)
    def append_log(self, text: str):
        """公开槽函数，用于向日志区域追加文本"""
        self.log_output.append(text)

    @Slot()
    def on_task_finished(self):
        """任务完成后，重置UI状态"""
        self.log_output.append("任务已完成！")
        self.start_task_button.setEnabled(True)
        self.start_task_button.setText("开始执行任务")
        self.progress_bar.setVisible(False)