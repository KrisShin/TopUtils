# main_window.py
import time
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox
from PySide6.QtCore import QThreadPool, Slot
from jose import jwt, JWTError

# 导入API客户端和辅助函数
from api_client import ApiClient # 假设您的 ApiClient 在这里
# from widgets.utils import is_running_in_vm # 假设 is_running_in_vm 在 widgets.utils
# 为了演示，我们直接从 api_client 导入，如果它在那里的话
from widgets.utils import is_running_in_vm

from worker import Worker
# 导入我们已经定义好的所有UI页面
from widgets.loading_page import LoadingPage
from widgets.setup_page import SetupPage
from widgets.login_page import LoginPage
from widgets.main_app_page import MainAppPage

class MainWindow(QMainWindow):
    def __init__(self, api_client: ApiClient):
        super().__init__()
        self.setWindowTitle("软件授权客户端")
        self.api = api_client
        self.thread_pool = QThreadPool()
        self.user_data = {}  # 用于存储解码后的token信息

        # --- 1. 初始化UI页面 ---
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        self.loading_page = LoadingPage()
        self.setup_page = SetupPage()

        self.stacked_widget.addWidget(self.loading_page)
        self.stacked_widget.addWidget(self.setup_page)

        # --- 2. 连接静态页面的信号 ---
        self.setup_page.email_submitted.connect(self.on_email_submitted)
        self.setup_page.totp_confirmed.connect(self.on_totp_confirmed)

        # --- 3. 启动应用初始流程 ---
        self.run_initial_check()

    # --- 通用工具方法 ---
    def run_in_background(self, fn, on_result, on_error=None, on_finished=None):
        worker = Worker(fn)
        worker.signals.result.connect(on_result)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_finished:
            worker.signals.finished.connect(on_finished)
        self.thread_pool.start(worker)

    def show_error(self, message: str):
        QMessageBox.critical(self, "错误", message)

    def show_info(self, message: str):
        QMessageBox.information(self, "提示", message)

    def show_page(self, page_widget):
        if self.stacked_widget.indexOf(page_widget) == -1:
            self.stacked_widget.addWidget(page_widget)
        self.stacked_widget.setCurrentWidget(page_widget)

    # ===================================================================
    # 流程一：应用启动时的初始检查
    # ===================================================================
    def run_initial_check(self):
        self.show_page(self.loading_page)
        self.loading_page.set_status("正在检查运行环境...")
        self.run_in_background(is_running_in_vm, self.on_vm_check_result)

    @Slot(object)
    def on_vm_check_result(self, is_vm):
        if is_vm:
            self.show_error("出于授权策略考虑，本软件禁止在虚拟机中使用。")
            self.close()
            return
        
        self.loading_page.set_status("正在绑定设备...")
        self.run_in_background(self.api.bind, self.on_bind_result)
    
    @Slot(object)
    def on_bind_result(self, result):
        order_id, error = result
        if error:
            self.show_error(f"设备绑定失败: {error}")
            self.close()
            return
        
        self.api.order_id = order_id
        self.loading_page.set_status("正在验证授权...")
        self.run_in_background(self.api.is_valid, self.on_valid_check_result)

    @Slot(object)
    def on_valid_check_result(self, result):
        token, error = result
        if error:
            self.show_error(f"授权验证失败: {error}")
            self.close()
            return
        
        try:
            secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.api.order_id))
            self.user_data = jwt.decode(token, secret_key, algorithms=["HS256"])
            self.user_data['order_id'] = self.api.order_id # 确保order_id也存入user_data
        except JWTError as e:
            self.show_error(f"令牌无效或已损坏: {e}")
            self.close()
            return

        if not self.user_data.get('email'):
            self.show_page(self.setup_page)
            self.setup_page.show_email_step() # 确保从第一步开始
        else:
            self.setup_login_page()

    # ===================================================================
    # 流程二：首次设置 (绑定邮箱和TOTP)
    # ===================================================================
    @Slot(str)
    def on_email_submitted(self, email):
        self.user_data['email'] = email # 存储邮箱
        self.loading_page.set_status(f"正在为 {email} 请求TOTP授权...")
        self.show_page(self.loading_page)
        self.run_in_background(
            lambda: self.api.setup_totp(self.user_data['order_id']),
            self.on_totp_uri_received,
            on_finished=self.setup_page.reset_buttons # 确保按钮在API调用后重置
        )

    @Slot(object)
    def on_totp_uri_received(self, result):
        uri, error = result
        # 【重要】重置按钮状态，无论成功与否，SetupPage的按钮都应该可以再次操作
        # self.setup_page.reset_buttons() # 移到 run_in_background 的 on_finished

        if error:
            self.show_error(f"获取TOTP信息失败: {error}")
            self.show_page(self.setup_page) # 返回SetupPage让用户重试
            self.setup_page.show_email_step() # 确保回到邮件输入步骤
            return

        # 【新增】对URI进行更严格的校验
        if not uri or not isinstance(uri, str) or not uri.startswith("otpauth://"):
            self.show_error("服务器返回的TOTP URI无效，请重试。")
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return
        
        # URI有效，才显示TOTP步骤
        self.setup_page.show_totp_step(uri)
        # 注意：此时MainWindow仍然显示的是LoadingPage，
        # show_totp_step会切换SetupPage内部的stacked_widget。
        # 我们需要确保MainWindow也切换到SetupPage。
        self.show_page(self.setup_page) # 确保SetupPage是当前主页面


    @Slot(str)
    def on_totp_confirmed(self, code):
        self.loading_page.set_status("正在确认TOTP...") # 提供反馈
        self.show_page(self.loading_page)
        self.run_in_background(
            lambda: self.api.confirm_totp(self.user_data['order_id'], self.user_data['email'], code),
            self.on_totp_confirm_result,
            on_finished=self.setup_page.reset_buttons # 确保按钮在API调用后重置
        )

    @Slot(object)
    def on_totp_confirm_result(self, result):
        data, error = result
        # self.setup_page.reset_buttons() # 移到 run_in_background 的 on_finished

        if error:
            self.show_error(f"TOTP确认失败: {error}")
            self.show_page(self.setup_page) # 返回SetupPage让用户重试
            self.setup_page.show_totp_step(self.user_data.get('_last_uri_for_retry', '')) # 尝试恢复上次的URI
            return
        
        self.show_info("绑定成功！现在请登录。")
        self.setup_login_page()

    # ===================================================================
    # 流程三：用户登录
    # ===================================================================
    def setup_login_page(self):
        # 惰性加载LoginPage，确保每次都是新的实例或正确更新
        if not hasattr(self, 'login_page') or self.login_page is None:
            self.login_page = LoginPage(email=self.user_data['email'])
            self.login_page.login_requested.connect(self.on_login_requested)
            self.login_page.email_code_requested.connect(self.on_email_code_requested)
            self.stacked_widget.addWidget(self.login_page) # 只添加一次
        else:
            # 如果页面已存在，可能需要更新其状态（例如，如果邮箱可以更改）
            self.login_page.user_email = self.user_data['email'] # 示例：更新邮箱显示
            self.login_page.reset_login_buttons() # 确保按钮是可用的

        self.show_page(self.login_page)


    @Slot(str, str)
    def on_login_requested(self, method_type, code): # method -> method_type 避免与内置方法冲突
        self.login_page.on_login_start()
        self.run_in_background(
            lambda: self.api.login(self.user_data['order_id'], code, method_type),
            self.on_login_result,
            on_finished=self.login_page.reset_login_buttons
        )

    @Slot()
    def on_email_code_requested(self):
        self.login_page.send_code_button.setText("发送中...")
        self.login_page.send_code_button.setEnabled(False)
        self.run_in_background(
            lambda: self.api.send_email_code(self.user_data['order_id']),
            self.on_email_code_sent_result
        )
    
    @Slot(object)
    def on_email_code_sent_result(self, result):
        data, error = result
        success = error is None
        message = data.get("message", "已发送") if success else error
        self.login_page.on_email_code_sent(success, message)


    @Slot(object)
    def on_login_result(self, result):
        data, error = result
        if error:
            self.show_error(f"登录失败: {error}")
            # 此处可以添加逻辑，如果错误是设备不匹配，则触发换绑流程
            # 例如: if "设备不匹配" in error or (data and data.get("status_code") == 403):
            #           self.handle_rebind_flow()
            return
        
        self.setup_main_app_page()

    # ===================================================================
    # 流程四：主应用
    # ===================================================================
    def setup_main_app_page(self):
        if not hasattr(self, 'main_app_page') or self.main_app_page is None:
            self.main_app_page = MainAppPage(email=self.user_data['email'])
            self.main_app_page.task_requested.connect(self.on_task_requested)
            self.stacked_widget.addWidget(self.main_app_page)
        else:
            # 更新可能已存在的页面
            self.main_app_page.welcome_label.setText(f"授权成功！欢迎您，{self.user_data['email']}")
        self.show_page(self.main_app_page)

    @Slot()
    def on_task_requested(self):
        def dummy_task():
            # 模拟一个耗时任务
            for i in range(101):
                time.sleep(0.02)
                # 如果需要更新进度条，可以在这里发出信号
            return "任务结果数据"
        
        self.main_app_page.append_log("开始执行模拟任务...") # 先在主线程更新UI
        self.run_in_background(
            dummy_task,
            lambda res: self.main_app_page.append_log(f"任务成功完成，结果: {res}"),
            on_error=lambda err: self.main_app_page.append_log(f"任务失败: {err}"),
            on_finished=self.main_app_page.on_task_finished
        )

    # (如果需要，可以在这里添加 handle_rebind_flow 等其他流程)

