import sys
import time
import threading
import pyautogui
import keyboard  # 用于全局热key监听
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PySide6.QtCore import Qt, QThread, Signal

# --- 自动点击工作线程 ---
class ClickWorker(QThread):
    # status_update = Signal(str) # 如果需要更详细的状态更新，可以取消注释

    def __init__(self, interval=1.0): # 默认间隔1秒，符合新规
        super().__init__()
        self.interval = interval
        self._is_running = False
        self._stop_event = threading.Event()

    def run(self):
        self._is_running = True
        self._stop_event.clear()
        print(f"自动点击已启动，间隔时间: {self.interval} 秒。热键: Ctrl+Shift+F12 停止。")
        # self.status_update.emit(f"自动点击已启动，间隔: {self.interval}s")
        try:
            while not self._stop_event.is_set():
                if self._is_running:
                    pyautogui.click()
                    print("点击!")
                    # self.status_update.emit("点击!")
                    self._stop_event.wait(self.interval)
                else:
                    break
        except Exception as e:
            print(f"点击线程出错: {e}")
            # self.status_update.emit(f"错误: {e}")
        finally:
            self._is_running = False
            print("自动点击已停止。")
            # self.status_update.emit("自动点击已停止。")

    def start_clicking(self, interval=None):
        if interval is not None:
            self.interval = interval
        if not self._is_running:
            self._is_running = True
            self._stop_event.clear()
            if not self.isRunning():
                self.start()
            print(f"尝试启动点击，当前运行状态: {self.isRunning()}, _is_running: {self._is_running}")


    def stop_clicking(self):
        print("尝试停止点击...")
        self._is_running = False
        self._stop_event.set()

    def is_active(self):
        return self._is_running and self.isRunning()

# --- 主窗口 ---
class AutoClickerApp(QWidget):
    HOTKEY_START = 'ctrl+shift+t'
    HOTKEY_STOP = 'ctrl+shift+y'

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"自动点击器 ({self.HOTKEY_START}启动, {self.HOTKEY_STOP}停止)")
        self.setGeometry(300, 300, 350, 180) # 稍微加宽一点点以适应新的按键名称

        self.click_worker = ClickWorker(interval=1.0)

        layout = QVBoxLayout()

        self.interval_label = QLabel("点击间隔时间 (秒, 必须 >= 1):")
        layout.addWidget(self.interval_label)

        self.interval_input = QLineEdit("30") # 默认值30秒
        self.interval_input.setPlaceholderText("例如: 1, 5, 10")
        layout.addWidget(self.interval_input)

        self.status_label = QLabel("状态: 未运行")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        # self.click_worker.status_update.connect(self.update_status_label)

        self.toggle_button = QPushButton(f"通过热键 {self.HOTKEY_START} / {self.HOTKEY_STOP} 控制")
        self.toggle_button.setEnabled(False)
        layout.addWidget(self.toggle_button)

        self.setLayout(layout)
        self.setup_hotkeys()

    # def update_status_label(self, message):
    #     self.status_label.setText(f"状态: {message}")

    def get_interval(self):
        try:
            interval = float(self.interval_input.text())
            if interval < 1: # 修改：间隔时间必须大于或等于1秒
                QMessageBox.warning(self, "输入错误", "间隔时间必须大于或等于1秒。")
                return None
            return interval
        except ValueError:
            QMessageBox.warning(self, "输入错误", "请输入有效的数字作为间隔时间。")
            return None

    def start_action(self):
        if self.click_worker.is_active():
            print("自动点击已经在运行中。")
            self.status_label.setText(f"状态: 已在运行 ({self.HOTKEY_STOP}停止)")
            return

        interval = self.get_interval()
        if interval is not None:
            print(f"准备启动点击，间隔: {interval}")
            self.click_worker.start_clicking(interval)
            self.status_label.setText(f"状态: 运行中... (间隔: {interval}s, {self.HOTKEY_STOP}停止)")
        else:
            self.status_label.setText(f"状态: 间隔时间无效 ({self.HOTKEY_START}启动)")


    def stop_action(self):
        if not self.click_worker.is_active() and not self.click_worker._is_running:
            print("自动点击未运行或已停止。")
            self.status_label.setText(f"状态: 未运行 ({self.HOTKEY_START}启动)")
            return

        print("接收到停止指令")
        self.click_worker.stop_clicking()
        self.status_label.setText(f"状态: 已停止 ({self.HOTKEY_START}启动)")


    def setup_hotkeys(self):
        try:
            keyboard.add_hotkey(self.HOTKEY_START, self.on_start_pressed)
            keyboard.add_hotkey(self.HOTKEY_STOP, self.on_stop_pressed)
            print(f"热键 {self.HOTKEY_START} (启动) 和 {self.HOTKEY_STOP} (停止) 已注册。")
            self.status_label.setText(f"状态: 等待操作 ({self.HOTKEY_START}启动)")
        except Exception as e:
            print(f"注册热键失败: {e}")
            QMessageBox.critical(self, "热键错误", f"无法注册热键 {self.HOTKEY_START}/{self.HOTKEY_STOP}。\n错误信息: {e}\n请确保没有其他程序占用了这些热键，并尝试以管理员权限运行。")
            self.status_label.setText("状态: 热键注册失败!")


    def on_start_pressed(self):
        print(f"{self.HOTKEY_START} 按下 - 尝试启动")
        self.start_action()

    def on_stop_pressed(self):
        print(f"{self.HOTKEY_STOP} 按下 - 尝试停止")
        self.stop_action()

    def closeEvent(self, event):
        print("关闭应用程序...")
        self.click_worker.stop_clicking()
        if self.click_worker.isRunning():
            self.click_worker.wait()
        keyboard.remove_all_hotkeys()
        print("热键已移除，线程已停止。再见！")
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = AutoClickerApp()
    window.show()
    sys.exit(app.exec())