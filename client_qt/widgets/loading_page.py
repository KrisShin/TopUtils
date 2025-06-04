# widgets/loading_page.py

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class LoadingPage(QWidget):
    """
    一个简单的加载页面，用于显示初始化过程中的状态文本。
    """
    def __init__(self):
        super().__init__()

        # --- 布局 ---
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # --- 控件 ---
        self.status_label = QLabel("正在初始化，请稍候...")
        font = self.status_label.font()
        font.setPointSize(12)
        self.status_label.setFont(font)
        self.status_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.status_label)

    def set_status(self, text: str):
        """
        公开方法，用于从外部更新状态标签的文本。
        例如: "正在检查环境...", "正在绑定设备..."
        """
        self.status_label.setText(text)