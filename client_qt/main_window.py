# main_window.py
import time
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox
from PySide6.QtCore import QThreadPool, Slot
from jose import jwt, JWTError

# 导入API客户端和辅助函数
from api_client import ApiClient  # 假设您的 ApiClient 在这里
from widgets.utils import is_running_in_vm  # 从 widgets.utils 导入

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
        self.rebind_target_order_id = None  # 用于存储换绑时的目标订单ID
        self.current_auth_operation = "login"  # "login" 或 "rebind_auth"

        # --- 1. 初始化UI页面 ---
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.loading_page = LoadingPage()
        self.setup_page = SetupPage()
        # LoginPage 和 MainAppPage 将在需要时惰性加载

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
        elif on_error is None:
            worker.signals.error.connect(lambda e_str: self.show_error(f"后台任务执行出错: {e_str}"))
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
        if error or not token:  # 如果is_valid报错或未返回token，则认为是新绑定
            # self.show_error(f"授权验证失败: {error}. 这可能是一个新绑定，请继续设置。")
            self.user_data['order_id'] = self.api.order_id
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return

        try:
            secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.api.order_id))
            self.user_data = jwt.decode(token, secret_key, algorithms=["HS256"])
            self.user_data['order_id'] = self.api.order_id
        except JWTError as e:
            self.show_error(f"令牌无效或已损坏: {e}")
            self.user_data['order_id'] = self.api.order_id  # 即使token解析失败，order_id还是要设置
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return

        if not self.user_data.get('email'):
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
        else:
            self.setup_login_page(mode="login")  # 初始进入登录模式

    # ===================================================================
    # 流程二：首次设置 / 邮箱输入 / 换绑判断
    # ===================================================================
    @Slot(str)
    def on_email_submitted(self, email):
        self.user_data['email'] = email
        self.loading_page.set_status(f"正在检查 {email} 订阅状态...")
        self.show_page(self.loading_page)
        self.run_in_background(
            lambda: self.api.check_order_exist(email=self.user_data['email'], current_order_id=self.api.order_id),
            self.on_check_email_status_result,
            on_finished=self.setup_page.reset_buttons,
        )

    @Slot(object)
    def on_check_email_status_result(self, result):
        data, error = result
        if error:
            self.show_error(f"检查邮箱状态失败: {error}")
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return

        status = data.get("status")
        if status == "ok":
            self.loading_page.set_status(f"为新用户 {self.user_data['email']} 请求TOTP授权...")
            self.show_page(self.loading_page)
            self.run_in_background(lambda: self.api.setup_totp(self.api.order_id), self.on_totp_uri_received, on_finished=self.setup_page.reset_buttons)
        elif status == "rebind_required":
            self.rebind_target_order_id = data.get("existing_order_id")
            reply = QMessageBox.question(
                self,
                "设备换绑确认",
                f"邮箱 {self.user_data['email']} 已在另一台设备上激活此工具。\n" f"是否要将授权转移到当前设备？\n" f"（原设备将需要重新激活）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                # ---【新逻辑起点】---
                # 用户同意换绑，进入换绑前的身份验证步骤
                self.show_info("为了安全，请先验证您的身份以完成设备换绑。")
                self.setup_login_page(mode="rebind_auth")  # 使用登录页进行换绑验证
                # ---【新逻辑终点】---
            else:
                self.show_page(self.setup_page)
                self.setup_page.show_email_step()
        elif status == "login_required":
            self.api.order_id = data.get("existing_order_id", self.api.order_id)
            self.user_data['order_id'] = self.api.order_id
            self.show_info("账户已存在，请直接登录。")
            self.setup_login_page(mode="login")
        else:
            self.show_error(f"未知的邮箱状态: {status}")
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()

    # --- （首次设置TOTP的 on_totp_uri_received, on_totp_confirmed, on_totp_confirm_result 保持不变）---
    @Slot(object)
    def on_totp_uri_received(self, result):  # 主要用于首次设置
        uri, error = result
        if error:
            self.show_error(f"获取TOTP信息失败: {error}")
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return
        if not uri or not isinstance(uri, str) or not uri.startswith("otpauth://"):
            self.show_error("服务器返回的TOTP URI无效，请重试。")
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return
        self.user_data['_last_uri_for_retry'] = uri
        self.setup_page.show_totp_step(uri)
        self.show_page(self.setup_page)

    @Slot(str)
    def on_totp_confirmed(self, code):  # 主要用于首次设置
        self.loading_page.set_status("正在确认首次TOTP绑定...")
        self.show_page(self.loading_page)
        self.run_in_background(
            lambda: self.api.confirm_totp(self.user_data['order_id'], self.user_data['email'], code),
            self.on_totp_confirm_result,
            on_finished=self.setup_page.reset_buttons,
        )

    @Slot(object)
    def on_totp_confirm_result(self, result):  # 主要用于首次设置
        data, error = result
        if error:
            self.show_error(f"TOTP确认失败: {error}")
            self.show_page(self.setup_page)
            self.setup_page.show_totp_step(self.user_data.get('_last_uri_for_retry', ''))
            return
        self.show_info("身份验证器绑定成功！欢迎使用。")
        self.setup_main_app_page()

    # ===================================================================
    # 流程三：用户登录 / 换绑身份验证
    # ===================================================================
    def setup_login_page(self, mode: str = "login"):
        self.current_auth_operation = mode  # 设置当前操作模式

        if not hasattr(self, 'auth_page_instance') or self.auth_page_instance is None:
            self.auth_page_instance = LoginPage(email=self.user_data['email'])
            # 根据模式连接不同的信号处理槽
            if mode == "login":
                self.auth_page_instance.login_requested.connect(self.on_login_requested_slot)
                self.auth_page_instance.email_code_requested.connect(self.on_login_email_code_requested_slot)
            elif mode == "rebind_auth":
                self.auth_page_instance.login_requested.connect(self.on_rebind_auth_code_submitted_slot)
                self.auth_page_instance.email_code_requested.connect(self.on_rebind_auth_email_code_requested_slot)
            self.stacked_widget.addWidget(self.auth_page_instance)
        else:
            # 如果页面已存在，更新其状态并重新连接信号以匹配当前模式
            self.auth_page_instance.user_email = self.user_data['email']
            self.auth_page_instance.welcome_label.setText(f"授权验证 - {self.user_data['email']}" if mode == "rebind_auth" else f"你好, {self.user_data['email']}")
            self.auth_page_instance.reset_login_buttons()

            # 断开旧连接，连接新模式的槽
            try:
                self.auth_page_instance.login_requested.disconnect()
            except RuntimeError:
                pass  # 如果没有连接，会抛出错误，忽略
            try:
                self.auth_page_instance.email_code_requested.disconnect()
            except RuntimeError:
                pass

            if mode == "login":
                self.auth_page_instance.login_requested.connect(self.on_login_requested_slot)
                self.auth_page_instance.email_code_requested.connect(self.on_login_email_code_requested_slot)
            elif mode == "rebind_auth":
                self.auth_page_instance.login_requested.connect(self.on_rebind_auth_code_submitted_slot)
                self.auth_page_instance.email_code_requested.connect(self.on_rebind_auth_email_code_requested_slot)

        self.show_page(self.auth_page_instance)

    # --- 常规登录的槽函数 ---
    @Slot(str, str)
    def on_login_requested_slot(self, method_type, code):
        self.auth_page_instance.on_login_start()
        self.run_in_background(
            lambda: self.api.login(self.user_data['order_id'], code, method_type),
            self.on_login_result,  # 连接到常规登录结果处理
            on_finished=self.auth_page_instance.reset_login_buttons,
        )

    @Slot()
    def on_login_email_code_requested_slot(self):
        self.auth_page_instance.send_code_button.setText("发送中...")
        self.auth_page_instance.send_code_button.setEnabled(False)
        # 常规登录时，邮件码是针对当前 user_data['order_id'] 的邮箱 self.user_data['email']
        self.run_in_background(
            lambda: self.api.send_email_code(self.api.order_id),  # 假设send_email_code通过email和tool_code定位
            self.on_auth_email_code_sent_result,  # 通用处理邮件码发送结果
        )

    # --- 换绑验证的槽函数 ---
    @Slot(str, str)
    def on_rebind_auth_code_submitted_slot(self, check_method, code):
        """当为换绑验证提交验证码时"""
        self.auth_page_instance.on_login_start()  # 复用按钮状态
        self.run_in_background(
            lambda: self.api.rebind(email=self.user_data['email'], check_method=check_method, code=code),
            self.on_rebind_finished_result,
            on_finished=self.auth_page_instance.reset_login_buttons,
        )

    @Slot()
    def on_rebind_auth_email_code_requested_slot(self):
        """当为换绑验证请求邮件码时"""
        self.auth_page_instance.send_code_button.setText("发送中...")
        self.auth_page_instance.send_code_button.setEnabled(False)
        self.run_in_background(
            lambda: self.api.send_email_code(order_id=self.rebind_target_order_id),
            self.on_auth_email_code_sent_result,  # 通用处理邮件码发送结果
        )

    @Slot(object)
    def on_rebind_finished_result(self, result):  # 已存在，处理换绑API调用后的结果
        token, error = result
        if error:
            self.show_error(f"设备换绑失败: {error}")
            self.show_page(self.setup_page)  # 失败则回到设置流程起点
            self.setup_page.show_email_step()
            return
        secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.rebind_target_order_id, self.user_data['email']))
        self.user_data = jwt.decode(token, secret_key, algorithms=["HS256"])
        self.rebind_target_order_id = None
        self.api.order_id = self.rebind_target_order_id
        self.user_data['order_id'] = self.rebind_target_order_id
        self.show_info("设备换绑成功！24小时内只能换绑一次")

        self.loading_page.set_status(f"为换绑订单 {self.api.order_id} 请求TOTP...")
        self.setup_main_app_page()

    # --- 通用邮件码发送结果处理 ---
    @Slot(object)
    def on_auth_email_code_sent_result(self, result):  # 改为通用名
        data, error = result
        success = error is None
        message = data.get("message", "已发送") if success else (error or "发送失败")

        if hasattr(self, 'auth_page_instance') and self.auth_page_instance:
            self.auth_page_instance.on_email_code_sent(success, message)

    # --- 常规登录成功后的处理 ---
    @Slot(object)
    def on_login_result(self, result):
        data, error = result
        if error:
            self.show_error(f"登录失败: {error}")
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
            self.main_app_page.welcome_label.setText(f"授权成功！欢迎您，{self.user_data['email']}")
        self.show_page(self.main_app_page)

    @Slot()
    def on_task_requested(self):
        def dummy_task():
            for i in range(101):
                time.sleep(0.02)
            return "任务结果数据"

        self.main_app_page.append_log("开始执行模拟任务...")
        self.run_in_background(
            dummy_task,
            lambda res: self.main_app_page.append_log(f"任务成功完成，结果: {res}"),
            on_error=lambda err_str: self.main_app_page.append_log(f"任务失败: {err_str}"),
            on_finished=self.main_app_page.on_task_finished,
        )
