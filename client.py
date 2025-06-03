# client.py
from typing import Optional
import httpx
import json
import time
import os
import platform
import hashlib
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.progress import track
import subprocess
import psutil
from jose import jwt

# --- 配置 ---
BASE_URL = "http://127.0.0.1:36000/api"  # 您的 FastAPI 服务器地址
CONFIG_FILE = "config.json"
TOOL_CODE = '2ab2171ad8ba4521baf98ac5ff78a746'

# 使用 rich 提供更好的命令行体验
console = Console()


def is_running_in_vm():
    """
    通过检查硬件制造商信息和网卡MAC地址来判断是否在虚拟机中运行。
    返回 True 如果检测到是虚拟机，否则返回 False。
    """
    # 转换为小写以便于不区分大小写的比较
    vm_keywords = ["vmware", "virtualbox", "qemu", "kvm", "hyper-v", "microsoft corporation", "innotek gmbh", "parallels"]
    vm_mac_prefixes = ["00:05:69", "00:0C:29", "00:1C:42", "08:00:27", "00:50:56"]

    # --- 1. 检查网卡MAC地址前缀 (跨平台) ---
    try:
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == psutil.AF_LINK:
                    mac_prefix = addr.address[:8].upper()
                    if mac_prefix in vm_mac_prefixes:
                        # print(f"检测到虚拟机MAC地址前缀: {mac_prefix}")
                        return True
    except Exception:
        pass  # 获取失败则继续

    # --- 2. 检查硬件制造商信息 (分平台) ---
    try:
        system = platform.system()
        vendor_info = ""

        if system == "Windows":
            # 检查系统制造商和BIOS信息
            vendor_info += subprocess.check_output('wmic csproduct get vendor', shell=True).decode().lower()
            vendor_info += subprocess.check_output('wmic bios get manufacturer', shell=True).decode().lower()

        elif system == "Linux":
            # 检查DMI信息
            if os.path.exists('/sys/class/dmi/id/sys_vendor'):
                with open('/sys/class/dmi/id/sys_vendor') as f:
                    vendor_info += f.read().lower()
            if os.path.exists('/sys/class/dmi/id/product_name'):
                with open('/sys/class/dmi/id/product_name') as f:
                    vendor_info += f.read().lower()

        elif system == "Darwin":  # macOS
            vendor_info += subprocess.check_output("ioreg -l | grep -E 'Manufacturer|Model'", shell=True).decode().lower()

        for keyword in vm_keywords:
            if keyword in vendor_info:
                # print(f"检测到虚拟机硬件关键词: {keyword}")
                return True

    except Exception:
        pass  # 命令执行失败则继续

    return False


# --- 硬件与配置管理 ---
def get_device_hash():
    """
    生成一个更健壮、更稳定的设备唯一标识符。
    它结合了主板序列号、CPU ID和所有物理网卡的MAC地址，并跨平台兼容。
    """
    system = platform.system()

    board_serial = ""
    cpu_id = ""
    mac_addresses = []

    try:
        # --- 获取主板和CPU信息 (OS-specific) ---
        if system == "Windows":
            # 使用WMIC命令行工具获取
            board_serial = subprocess.check_output('wmic baseboard get SerialNumber', shell=True).decode().split('\n')[1].strip()
            cpu_id = subprocess.check_output('wmic cpu get ProcessorId', shell=True).decode().split('\n')[1].strip()

        elif system == "Linux":
            # 从/sys/文件系统中读取，通常不需要root权限
            try:
                with open('/sys/class/dmi/id/board_serial') as f:
                    board_serial = f.read().strip()
            except Exception:
                # 备用方案：使用dmidecode，可能需要权限
                board_serial = subprocess.check_output('sudo dmidecode -s baseboard-serial-number', shell=True).decode().strip()

            # CPU信息通常在/proc/cpuinfo中，但没有统一的ID，我们组合关键信息
            cpu_info_raw = subprocess.check_output('cat /proc/cpuinfo', shell=True).decode()
            for line in cpu_info_raw.split('\n'):
                if "vendor_id" in line or "model name" in line:
                    cpu_id += line.split(':')[1].strip()

        elif system == "Darwin":  # macOS
            # 使用ioreg工具获取
            board_serial = subprocess.check_output("ioreg -l | grep IOPlatformSerialNumber", shell=True).decode().split('"')[3]
            # Mac的CPU ID不易直接获取，但主板序列号已足够唯一和稳定
            cpu_id = board_serial

        # --- 获取所有物理网卡的MAC地址 (使用psutil跨平台) ---
        # psutil比uuid.getnode()更可靠，能获取所有网卡
        for interface, addrs in psutil.net_if_addrs().items():
            # 过滤掉本地回环和没有MAC地址的接口
            if interface == 'lo' or not any(addr.family == psutil.AF_LINK for addr in addrs):
                continue
            for addr in addrs:
                if addr.family == psutil.AF_LINK:
                    mac_addresses.append(addr.address.upper())

        # 对MAC地址进行排序，确保每次生成的顺序都一致
        mac_addresses.sort()

    except Exception as e:
        # 如果获取任何硬件信息失败，打印错误但程序继续
        # 保证在特殊环境（如虚拟机、权限不足）下程序不会崩溃
        print(f"[警告] 获取硬件信息时出错: {e}。哈希可能不够准确。")

    # --- 组合并生成最终哈希 ---
    # 将所有获取到的信息拼接成一个长字符串
    # 即使某个信息获取失败（为空字符串），也不影响整体流程
    combined_string = f"BOARD:{board_serial}-CPU:{cpu_id}-MACS:{''.join(mac_addresses)}"

    # 使用SHA256生成哈希值
    final_hash = hashlib.sha256(combined_string.encode()).hexdigest()

    return final_hash


# --- API 客户端 ---
class ApiClient:
    """封装所有与后端API的交互"""

    def __init__(self, base_url):
        self.base_url = base_url
        self.tool_code = TOOL_CODE
        self.order_id = None  # 用于存储订单ID
        self.device_hash = get_device_hash()  # 获取当前设备的唯一标识符

    def setup_totp(self, order_id: str) -> Optional[str]:
        """请求服务器生成TOTP URI"""
        try:
            response = httpx.post(f"{self.base_url}/order/auth/setup-totp", json={"order_id": order_id})
            response.raise_for_status()  # 如果状态码不是2xx，则抛出异常
            # 返回JSON中的URI字符串
            return response.json().get("uri")
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]错误: 无法连接到服务器或服务器返回错误。 {e.response.json() if e.response else e}[/]")
            return None

    def confirm_totp(self, order_id: str, email: str, code: str):
        try:
            console.print({"order_id": order_id, "email": email, "code": code})
            response = httpx.post(f"{self.base_url}/order/auth/confirm-totp", json={"order_id": order_id, "email": email, "code": code})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]错误: {e.response.json()['detail']}[/]")
            return None

    def login(self, order_id: str, code: str):
        try:
            response = httpx.post(
                f"{self.base_url}/order/auth/login", json={"order_id": order_id, "code": code, "device_hash": self.device_hash}
            )
            return response
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]错误: 无法连接到服务器。 {e}[/]")
            return None

    def rebind(self, email: str, code: str):
        try:
            response = httpx.post(f"{self.base_url}/auth/rebind", json={"email": email, "code": code, "new_device_hash": self.device_hash})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]错误: {e.response.json()['detail']}[/]")
            return None

    def bind(self):
        try:
            response = httpx.post(f"{self.base_url}/order/bind", json={"tool_code": self.tool_code, "device_hash": self.device_hash})
            response.raise_for_status()
            return response.json()['data']['order_id']
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]错误: {e.response.json()['detail']}[/]")
            return None

    def is_valid(self):
        """检查当前设备是否有效"""
        try:
            response = httpx.post(f"{self.base_url}/order/is-valid", json={"order_id": self.order_id})
            response.raise_for_status()
            return response.json()['data']['token']
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]错误: {e.response.json()['detail']}[/]")
            return False


# --- 核心应用逻辑 ---
def run_trial_mode():
    """运行1分钟的试用模式"""
    console.print("\n[bold green]您已进入1分钟试用模式！[/]")
    for _ in track(range(60), description="试用时间剩余..."):
        time.sleep(1)
    console.print("\n[bold yellow]试用时间结束。请订阅并登录以继续使用。[/]")


def run_main_app_logic():
    """模拟主程序的核心功能"""
    console.print("\n[bold cyan]授权成功！欢迎使用本软件。[/]")
    console.print("正在执行核心功能...")
    time.sleep(5)
    console.print("[bold cyan]任务完成，感谢使用！[/]")


def handle_totp_setup(api: ApiClient, decode_token: dict) -> bool:
    """引导用户完成TOTP的设置，并在命令行显示二维码"""
    console.print("\n[bold yellow]为了您的账户安全，需要先绑定身份验证器。[/]")
    if not Confirm.ask("是否现在开始绑定？"):
        console.print("操作已取消。")
        return False

    console.print("正在向服务器请求授权信息...")
    # 现在 `uri` 是一个字符串，例如 'otpauth://...'
    uri = api.setup_totp(decode_token['order_id'])

    if uri:
        # --- 【核心修改】直接在命令行打印二维码 ---
        try:
            import qrcode as qr_lib

            qr = qr_lib.QRCode(border=1)
            qr.add_data(uri)
            qr.make(fit=True)

            console.print("\n[bold magenta]请使用微信搜索[腾讯身份验证器]小程序选择[二维码验证]扫描下方的二维码：[/]")
            # 直接在终端打印ASCII二维码
            qr.print_tty()
            console.print()  # 增加一个换行

        except ImportError:
            console.print("[bold red]错误：`qrcode` 库未安装，无法显示二维码。请运行 `pip install qrcode[pil]`[/]")
            return False
        # --- 【修改结束】 ---

        while True:
            code = Prompt.ask("请输入您验证器App上显示的6位数字码")
            result = api.confirm_totp(decode_token['order_id'], decode_token['email'], code)
            if result:
                console.print(f"[bold green]{result['message']}[/]")
                return True
    return False


def handle_rebind(api: ApiClient, email: str):
    """处理设备换绑"""
    console.print("\n[bold yellow]警告：检测到您正在一台新设备上登录。[/]")
    if not Confirm.ask("是否要将授权迁移到这台新设备？这将使您之前的设备失效。"):
        console.print("操作取消。")
        return False

    code = Prompt.ask("为了安全，请输入您验证器App上的6位数字码以确认操作")
    result = api.rebind(email, code, api.device_hash)
    if result:
        console.print(f"[bold green]{result['message']}[/]")
        return True
    return False


def main():
    """主函数"""
    console.print("[bold blue]--- 欢迎使用授权客户端Demo ---[/]")
    api = ApiClient(BASE_URL)
    if is_running_in_vm():
        console.print("\n[bold red]错误：检测到程序正在虚拟机环境下运行。[/]")
        console.print("[bold red]出于授权策略考虑，本软件禁止在虚拟机中使用。[/]")
        Prompt.ask("\n按任意键退出")
        return  # 直接退出程序
    api.order_id = api.bind()
    # console.print(f"本机设备ID: [cyan]{api.device_hash[:16]}...[/]")
    token = api.is_valid()
    if not token:
        console.print("\n[bold red]错误：当前设备未授权或已过期。[/]")
        Prompt.ask("\n按任意键退出")
        return  # 直接退出程序
    console.print(f"\n[bold green]设备授权成功！[/] 设备ID: [cyan]{api.device_hash[:16]}...[/]")
    console.print(f"[bold green]设备令牌: {token[:16]}[/]")

    decode_token = jwt.decode(token, '_'.join((api.tool_code, api.device_hash, api.order_id)), algorithms=["HS256"])
    if not decode_token['email']:
        console.print("[bold yellow]⚠️警告：请先绑定邮箱和设备[/]")
        email = Prompt.ask("\n请输入您的邮箱以用于后续登录")

        decode_token['email'] = email
        if not handle_totp_setup(api, decode_token):
            return  # TOTP设置失败或取消，退出程序

        # 【修改在这里】合并为一个 prompt 参数，并移除重复的关键字参数
        choice = Prompt.ask("检测到首次运行[bold green]按任意键开始试用 (1分钟)[/]\n")

        if choice == "1":
            run_trial_mode()
            # 试用结束后，强制进入登录流程

    # --- 主授权流程 ---
    console.print(f"\n你好, [bold cyan]{decode_token['email']}[/]。正在准备授权...")

    # --- 循环登录验证 ---
    while True:
        console.print("\n[bold]请输入授权码以继续...[/]")
        code = Prompt.ask("请输入您身份验证器App上的6位数字码")

        response = api.login(decode_token['order_id'], code)

        if not response:
            # API客户端内部已打印错误，直接重试
            continue

        if response.status_code == 200:
            run_main_app_logic()
            break  # 登录成功，退出循环
        elif response.status_code == 403:  # 设备不匹配
            # console.print(f"设备不匹配, 请重新绑定授权")
            # if handle_rebind(api, email):
            #     # 换绑成功后，直接进入主程序
            #     run_main_app_logic()
            #     break
            # else:
            #     # 换绑失败或取消
            #     console.print("授权失败，程序退出。")
            #     break
            ...
        else:
            # 其他错误，例如动态码错误(401)
            console.print(f"[bold red]登录失败: {response.json()['detail']}[/]")
            # 让用户重试


if __name__ == "__main__":
    main()
