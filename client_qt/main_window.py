# client_qt/main_window.py
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox
from PySide6.QtCore import QThreadPool, Slot, QTimer  # QTimerを追加
from jose import jwt, JWTError

from api_client import ApiClient
from widgets.utils import is_running_in_vm

from worker import Worker

from widgets.loading_page import LoadingPage
from widgets.setup_page import SetupPage
from widgets.login_page import LoginPage

# 确保从正确的路径导入 MainAppPage
from scripts.auto_click import WINDOW_TITLE, MainAppPage  # 假设它在 scripts 文件夹下


class MainWindow(QMainWindow):
    HEARTBEAT_INTERVAL_MS = 60 * 60 * 1000  # 定期全局权限心跳检测

    def __init__(self, api_client: ApiClient):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        # self.setWindowTitle("软件授权客户端")
        self.api = api_client
        self.thread_pool = QThreadPool()
        self.user_data = {}
        self.rebind_target_order_id = None
        self.current_auth_operation = "login"

        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        self.loading_page = LoadingPage()
        self.setup_page = SetupPage()
        # LoginPage 和 MainAppPage 将在需要时惰性加载
        self.main_app_page = None  # 初始化为 None
        self.auth_page_instance = None  # 初始化为 None

        self.stacked_widget.addWidget(self.loading_page)
        self.stacked_widget.addWidget(self.setup_page)

        self.setup_page.email_submitted.connect(self.on_email_submitted)
        self.setup_page.totp_confirmed.connect(self.on_totp_confirmed)

        # --- 心跳定时器 ---
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.perform_heartbeat_check)
        # ---

        self.run_initial_check()

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
        token_str, error = result  # is_valid 返回的是 token 字符串
        if error or not token_str:
            self.user_data['order_id'] = self.api.order_id
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return

        try:
            secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.api.order_id))
            decoded_token = jwt.decode(token_str, secret_key, algorithms=["HS256"])
            self.user_data = decoded_token  # 存储解码后的 token
            self.user_data['order_id'] = self.api.order_id  # 确保 order_id 也在 user_data 中
        except JWTError as e:
            self.show_error(f"令牌无效或已损坏: {e}")
            self.user_data['order_id'] = self.api.order_id
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return

        if not self.user_data.get('email'):
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
        else:
            self.setup_login_page(mode="login")

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
        if status == "ok":  # 新用户，或邮箱未绑定到其他订单
            self.loading_page.set_status(f"为新用户 {self.user_data['email']} 请求TOTP授权...")
            self.show_page(self.loading_page)
            # order_id 用于 setup_totp 应该是当前设备的 order_id
            self.run_in_background(lambda: self.api.setup_totp(self.api.order_id), self.on_totp_uri_received, on_finished=self.setup_page.reset_buttons)
        elif status == "rebind_required":  # 邮箱已绑定到其他订单
            self.rebind_target_order_id = data.get("existing_order_id")  # 这是旧设备的 order_id
            reply = QMessageBox.question(
                self,
                "设备换绑确认",
                f"邮箱 {self.user_data['email']} 已在另一台设备上激活此工具。\n" f"是否要将授权转移到当前设备？\n" f"（原设备将需要重新激活）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.show_info("为了安全，请先验证您的身份以完成设备换绑。")
                # 注意：此时 self.api.order_id 仍然是当前新设备的 order_id
                # rebind API 调用时，它会使用 self.api.device_hash (新设备的)
                # 而 rebind API 中的 order_id 参数应为 None 或当前 order_id (api_client.rebind 中处理)
                # self.api.order_id 将在 rebind 成功后更新为 rebind_target_order_id
                self.user_data['order_id'] = self.api.order_id  # 确保 user_data 中有 order_id
                self.api.order_id = self.api.order_id  # 确认 api.order_id 也是当前设备的
                self.setup_login_page(mode="rebind_auth")
            else:
                self.show_page(self.setup_page)
                self.setup_page.show_email_step()
        else:
            self.show_error(f"未知的邮箱状态: {status}")
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()

    @Slot(object)
    def on_totp_uri_received(self, result):
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
    def on_totp_confirmed(self, code):  # 首次设置 TOTP
        self.loading_page.set_status("正在确认首次TOTP绑定...")
        self.show_page(self.loading_page)
        # confirm_totp 使用的是当前设备的 order_id (self.user_data['order_id'] 应该等于 self.api.order_id)
        self.run_in_background(
            lambda: self.api.confirm_totp(self.user_data['order_id'], self.user_data['email'], code),
            self.on_totp_confirm_result,
            on_finished=self.setup_page.reset_buttons,
        )

    @Slot(object)
    def on_totp_confirm_result(self, result):  # 首次设置 TOTP 结果
        token_str, error = result  # confirm_totp 返回 token 字符串
        if error or not token_str:
            self.show_error(f"TOTP确认失败: {error or '未返回令牌'}")
            self.show_page(self.setup_page)
            self.setup_page.show_totp_step(self.user_data.get('_last_uri_for_retry', ''))
            return

        try:
            # 解码 confirm_totp 返回的 token
            secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.user_data['order_id']))
            decoded_token = jwt.decode(token_str, secret_key, algorithms=["HS256"])
            self.user_data.update(decoded_token)  # 更新 user_data
        except JWTError as e:
            self.show_error(f"首次绑定后的令牌解析失败: {e}")
            # 即使解析失败，也尝试进入主应用页，后续的心跳或操作会要求重新登录

        self.show_info("身份验证器绑定成功！欢迎使用。")
        self.setup_main_app_page()  # 使用更新后的 self.user_data

    def setup_login_page(self, mode: str = "login"):
        self.current_auth_operation = mode

        # LoginPage 初始化或更新
        if self.auth_page_instance is None:
            self.auth_page_instance = LoginPage(email=self.user_data.get('email', "用户"))  # 使用 get 避免 KeyError
            self.stacked_widget.addWidget(self.auth_page_instance)
        else:
            self.auth_page_instance.user_email = self.user_data.get('email', "用户")
            self.auth_page_instance.welcome_label.setText(
                f"授权验证 - {self.user_data.get('email', '用户')}" if mode == "rebind_auth" else f"你好, {self.user_data.get('email', '用户')}"
            )
            self.auth_page_instance.reset_login_buttons()

        # 断开旧连接 (放在前面，避免重复连接)
        try:
            self.auth_page_instance.login_requested.disconnect()
        except RuntimeError:
            pass
        try:
            self.auth_page_instance.email_code_requested.disconnect()
        except RuntimeError:
            pass

        # 根据模式连接信号
        if mode == "login":
            self.auth_page_instance.login_requested.connect(self.on_login_requested_slot)
            self.auth_page_instance.email_code_requested.connect(self.on_login_email_code_requested_slot)
        elif mode == "rebind_auth":
            self.auth_page_instance.login_requested.connect(self.on_rebind_auth_code_submitted_slot)  # 连接到换绑验证码提交
            self.auth_page_instance.email_code_requested.connect(self.on_rebind_auth_email_code_requested_slot)  # 连接到换绑邮件码请求

        self.show_page(self.auth_page_instance)

    @Slot(str, str)
    def on_login_requested_slot(self, method_type, code):  # 常规登录
        self.auth_page_instance.on_login_start()
        # login API 使用当前设备的 order_id
        current_order_id = self.user_data.get('order_id', self.api.order_id)
        if not current_order_id:
            self.show_error("无法获取订单ID进行登录。")
            self.auth_page_instance.reset_login_buttons()
            return
        self.run_in_background(
            lambda: self.api.login(current_order_id, code, method_type),
            self.on_login_result,
            on_finished=self.auth_page_instance.reset_login_buttons,
        )

    @Slot()
    def on_login_email_code_requested_slot(self):  # 常规登录邮件码
        self.auth_page_instance.send_code_button.setText("发送中...")
        self.auth_page_instance.send_code_button.setEnabled(False)
        current_order_id = self.user_data.get('order_id', self.api.order_id)
        if not current_order_id:
            self.show_error("无法获取订单ID发送邮件码。")
            self.auth_page_instance.on_email_code_sent(False, "内部错误")
            return
        self.run_in_background(
            lambda: self.api.send_email_code(order_id=current_order_id),
            self.on_auth_email_code_sent_result,
        )

    @Slot(str, str)
    def on_rebind_auth_code_submitted_slot(self, check_method, code):  # 换绑验证提交
        self.auth_page_instance.on_login_start()
        self.api.order_id = self.api.order_id  # 确保是当前设备的 order_id (即新设备)
        # Rebind API 应该基于 email 找到旧订单
        self.run_in_background(
            lambda: self.api.rebind(email=self.user_data['email'], check_method=check_method, code=code),
            self.on_rebind_finished_result,
            on_finished=self.auth_page_instance.reset_login_buttons,
        )

    @Slot()
    def on_rebind_auth_email_code_requested_slot(self):  # 换绑验证邮件码
        self.auth_page_instance.send_code_button.setText("发送中...")
        self.auth_page_instance.send_code_button.setEnabled(False)
        # 发送邮件码时，是针对与该邮箱关联的已存在授权的订单 (即旧订单)
        # 所以应该使用 rebind_target_order_id
        if not self.rebind_target_order_id:
            self.show_error("换绑目标订单ID未知，无法发送邮件码。")
            self.auth_page_instance.on_email_code_sent(False, "内部错误")
            return
        self.run_in_background(
            lambda: self.api.send_email_code(order_id=self.rebind_target_order_id),
            self.on_auth_email_code_sent_result,
        )

    @Slot(object)
    def on_rebind_finished_result(self, result):
        token_str, error = result  # rebind API 返回新 token 字符串
        if error or not token_str:
            self.show_error(f"设备换绑失败: {error or '未返回令牌'}")
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return

        # 换绑成功后，API 返回的 token 是针对新设备和旧订单的组合
        # 所以解码时，order_id 应该是 rebind_target_order_id (即旧的那个，现在绑定到新设备了)
        # device_hash 是当前新设备的 self.api.device_hash
        try:
            secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.rebind_target_order_id, self.user_data['email']))
            decoded_token = jwt.decode(token_str, secret_key, algorithms=["HS256"])

            # 更新 MainWindow 的核心状态
            self.api.order_id = self.rebind_target_order_id  # 非常重要：更新当前活动的 order_id
            self.user_data = decoded_token
            self.user_data['order_id'] = self.api.order_id  # 确保 user_data 也同步

        except JWTError as e:
            self.show_error(f"换绑后令牌解析失败: {e}")
            self.show_page(self.setup_page)
            self.setup_page.show_email_step()
            return

        self.rebind_target_order_id = None  # 清理
        self.show_info("设备换绑成功！")  # 24小时限制由后端控制
        self.setup_main_app_page()  # 使用更新后的 self.user_data (包含了换绑后的授权信息)

    @Slot(object)
    def on_auth_email_code_sent_result(self, result):
        data, error = result
        success = error is None
        message = data.get("message", "已发送") if success else (error or "发送失败")
        if hasattr(self, 'auth_page_instance') and self.auth_page_instance:
            self.auth_page_instance.on_email_code_sent(success, message)

    @Slot(object)
    def on_login_result(self, result):  # 常规登录结果
        token_str, error = result  # login API 返回 token 字符串
        if error or not token_str:
            self.show_error(f"登录失败: {error or '未返回令牌'}")
            # 不切换页面，让用户在登录页重试
            return

        # 登录成功，解码 token 并更新 user_data
        try:
            secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.api.order_id, self.user_data['email']))
            decoded_token = jwt.decode(token_str, secret_key, algorithms=["HS256"])
            current_order_id = decoded_token.get('order_id', self.api.order_id)
            self.user_data=decoded_token  # 覆盖 user_data
            self.user_data['order_id'] = current_order_id  # 再次确保
            self.api.order_id = current_order_id  # 更新 api.order_id
        except JWTError as e:
            self.show_error(f"登录后令牌解析失败: {e}")
            # 即使解析失败，也可能需要一个不同的流程，或者强制重新setup
            return  # 停留在登录页或回到setup页

        self.setup_main_app_page()

    def setup_main_app_page(self):
        if self.main_app_page is None:
            self.main_app_page = MainAppPage(
                email=self.user_data.get('email', '未知用户'),
                api_client_instance=self.api,
                thread_pool_instance=self.thread_pool,
            )
            self.main_app_page.authorization_required.connect(self.handle_auth_required_from_app)
            # --- 连接 MainAppPage 的新信号 ---
            self.main_app_page.script_started.connect(self.on_script_started)
            self.main_app_page.script_stopped.connect(self.on_script_stopped)
            # ---
            self.stacked_widget.addWidget(self.main_app_page)
        else:
            # 如果页面已存在，用新的授权信息更新它
            self.main_app_page.user_email = self.user_data.get('email', '未知用户')
            self.main_app_page.welcome_label.setText(f"授权成功！欢迎您，{self.user_data.get('email', '未知用户')}")
            # 传递新的 token 数据给 MainAppPage 处理
            self.main_app_page.handle_authorization_status(self.user_data)

        self.show_page(self.main_app_page)

    @Slot()
    def handle_auth_required_from_app(self):
        self.show_info("您的授权已过期或需要验证，请重新登录。")
        self.heartbeat_timer.stop()  # 如果脚本因为内部授权问题停止，也停止心跳
        # self.user_data 清理一部分敏感信息可能比较好，或者保留 email
        # self.user_data = {'order_id': self.api.order_id, 'email': self.user_data.get('email')}
        self.setup_login_page(mode="login")

    # --- 心跳逻辑 ---
    @Slot()
    def on_script_started(self):
        """当 MainAppPage 中的脚本成功启动时调用"""
        print("[MainWindow] Script started, starting heartbeat.")
        if self.main_app_page:  # 确保页面存在
            self.main_app_page.append_log("心跳检测已启动。")
        # 立即执行一次检查（可选，或者等待第一个 interval）
        self.perform_heartbeat_check()
        self.heartbeat_timer.start(self.HEARTBEAT_INTERVAL_MS)

    @Slot()
    def on_script_stopped(self):
        """当 MainAppPage 中的脚本停止时调用（无论原因）"""
        print("[MainWindow] Script stopped, stopping heartbeat.")
        if self.main_app_page:  # 确保页面存在
            self.main_app_page.append_log("心跳检测已停止。")
        self.heartbeat_timer.stop()

    @Slot()
    def perform_heartbeat_check(self):
        """执行心跳检查，调用 API 验证订阅状态"""
        if not self.api.order_id:
            print("[Heartbeat] No order_id, skipping check.")
            self.heartbeat_timer.stop()  # 防止没有 order_id 时 계속 실행
            return

        print(f"[Heartbeat] Performing check for order_id: {self.api.order_id}")
        if self.main_app_page:
            self.main_app_page.append_log("正在执行心跳订阅检查...")

        # api.check_subscription_status 期望 order_id
        self.run_in_background(lambda: self.api.check_subscription_status(), self.on_heartbeat_check_result)

    @Slot(object)
    def on_heartbeat_check_result(self, result):
        token_str, error = result  # check_subscription_status 返回 (token_str, error)
        # token_str 是 JWT 字符串

        if error or not token_str:
            error_message = error or "心跳检查未返回有效令牌"
            print(f"[Heartbeat] Check failed: {error_message}")
            if self.main_app_page:
                self.main_app_page.append_log(f"心跳检查失败: {error_message}")
                self.main_app_page.force_stop_script("您的订阅已过期或验证失败，脚本已停止。\n请检查您的网络连接或续费后重试。")
            self.heartbeat_timer.stop()  # 发生错误或订阅无效，停止心跳
            # QMessageBox.warning(self, "订阅提醒", "您的订阅已过期或验证失败，脚本已停止。\n请续费后重试。")
            # 此处已由 force_stop_script 弹窗，不再重复
            # 根据具体策略，可能需要导航到登录页
            # self.handle_auth_required_from_app()
            return

        # 心跳检查成功，获得了新的 token_str
        try:
            secret_key = '_'.join((self.api.tool_code, self.api.device_hash, self.api.order_id, self.user_data.get('email', '')))
            new_decoded_token = jwt.decode(token_str, secret_key, algorithms=["HS256"])

            # 更新 MainWindow 的 user_data
            self.user_data.update(new_decoded_token)
            self.user_data['order_id'] = self.api.order_id  # 再次确保

            print("[Heartbeat] Check successful, token refreshed.")
            if self.main_app_page:
                self.main_app_page.append_log("心跳订阅检查成功，授权已刷新。")
                # 将新的授权信息传递给 MainAppPage 更新其内部状态 (如倒计时)
                self.main_app_page.handle_authorization_status(self.user_data)

            # 重启心跳计时器，进行下一次检查 (如果仍然 active)
            if self.heartbeat_timer.isActive():  # 如果上一次没被stop，则继续
                self.heartbeat_timer.start(self.HEARTBEAT_INTERVAL_MS)
            elif self.main_app_page and self.main_app_page.is_clicking_active:  # 如果因为某种原因停了但脚本还在跑，重新启动
                self.heartbeat_timer.start(self.HEARTBEAT_INTERVAL_MS)

        except JWTError as e:
            error_message = f"心跳检查成功但令牌解析失败: {e}"
            print(f"[Heartbeat] {error_message}")
            if self.main_app_page:
                self.main_app_page.append_log(error_message)
                self.main_app_page.force_stop_script("授权信息更新失败，脚本已停止。\n请尝试重新登录。")
            self.heartbeat_timer.stop()
            # QMessageBox.warning(self, "授权错误", "授权信息更新失败，脚本已停止。")
            # self.handle_auth_required_from_app()

    # --- 结束心跳逻辑 ---

    def closeEvent(self, event):
        self.heartbeat_timer.stop()  # 关闭时停止心跳
        if self.main_app_page:
            # 确保 MainAppPage 的 closeEvent 被调用以清理其资源
            # MainAppPage 的 closeEvent 通常由 QWidget 的关闭流程自动处理
            # 如果需要显式调用，可以 self.main_app_page.closeEvent(event)
            # 但通常不需要，除非 MainAppPage 不是一个 QWidget
            pass
        super().closeEvent(event)
