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


def execute_powershell_command(command: str) -> str:
    """
    执行 PowerShell 命令并返回其标准输出。
    """
    try:
        # 使用 'powershell -Command' 来执行命令
        # universal_newlines=True (或 text=True in Python 3.7+) 使输出为字符串
        # capture_output=True (Python 3.7+) 是 check_output 的现代替代
        result = subprocess.run(
            ["powershell", "-Command", command],
            capture_output=True,
            text=True,
            check=True,  # 如果命令返回非零退出码则抛出 CalledProcessError
            shell=True,  # 在Windows上，powershell可能需要shell=True才能找到
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"PowerShell command failed: {e.cmd}, Error: {e.stderr}")
        return ""
    except FileNotFoundError:
        print("PowerShell not found. Please ensure it is installed and in PATH.")
        return ""
    except Exception as e:
        print(f"An unexpected error occurred while executing PowerShell command: {e}")
        return ""


def is_running_in_vm():
    """
    通过检查硬件制造商信息和网卡MAC地址来判断是否在虚拟机中运行。
    返回 True 如果检测到是虚拟机，否则返回 False。
    """
    vm_keywords = [
        "vmware",
        "virtualbox",
        "qemu",
        "kvm",
        "hyper-v",
        "microsoft corporation",
        "innotek gmbh",
        "parallels",
        "xen",
    ]  # 添加 Xen
    vm_mac_prefixes = ["00:05:69", "00:0C:29", "00:1C:42", "08:00:27", "00:50:56", "00:16:3E"]  # 添加 Xen MAC

    try:
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == psutil.AF_LINK:  # AF_LINK 通常表示MAC地址
                    mac_prefix = addr.address[:8].upper()
                    if mac_prefix in vm_mac_prefixes:
                        # print(f"检测到虚拟机MAC地址前缀: {mac_prefix}")
                        return True
    except Exception as e:
        print(f"检查MAC地址时出错: {e}")
        pass

    try:
        system = platform.system()
        vendor_info_parts = []

        if system == "Windows":
            # 使用 PowerShell 获取系统制造商和BIOS信息
            # Get-WmiObject Win32_ComputerSystem | Select -ExpandProperty Manufacturer
            cs_manufacturer = execute_powershell_command(
                "Get-WmiObject -Class Win32_ComputerSystem | Select-Object -ExpandProperty Manufacturer"
            )
            if cs_manufacturer:
                vendor_info_parts.append(cs_manufacturer.lower())

            # Get-WmiObject Win32_BIOS | Select -ExpandProperty Manufacturer
            bios_manufacturer = execute_powershell_command("Get-WmiObject -Class Win32_BIOS | Select-Object -ExpandProperty Manufacturer")
            if bios_manufacturer:
                vendor_info_parts.append(bios_manufacturer.lower())

            # 检查 Hyper-V 特有的主板制造商
            baseboard_manufacturer = execute_powershell_command(
                "Get-WmiObject -Class Win32_BaseBoard | Select-Object -ExpandProperty Manufacturer"
            )
            if baseboard_manufacturer:
                vendor_info_parts.append(baseboard_manufacturer.lower())

        elif system == "Linux":
            dmi_paths = {
                "sys_vendor": "/sys/class/dmi/id/sys_vendor",
                "product_name": "/sys/class/dmi/id/product_name",
                "board_vendor": "/sys/class/dmi/id/board_vendor",  # 主板制造商
            }
            for key, path in dmi_paths.items():
                if os.path.exists(path):
                    try:
                        with open(path, 'r') as f:
                            vendor_info_parts.append(f.read().strip().lower())
                    except Exception as e:
                        print(f"读取DMI信息失败 {path}: {e}")

        elif system == "Darwin":  # macOS
            try:
                # ioreg 更倾向于获取Model Identifier和Manufacturer
                ioreg_output = subprocess.check_output(
                    "ioreg -l | grep -E 'IOPlatformExpertDevice|Manufacturer'", shell=True, text=True
                ).lower()
                vendor_info_parts.append(ioreg_output)
            except Exception as e:
                print(f"执行 ioreg 失败: {e}")

        combined_vendor_info = " ".join(vendor_info_parts)
        if combined_vendor_info:  # 仅当获取到信息时才检查
            for keyword in vm_keywords:
                if keyword in combined_vendor_info:
                    # print(f"检测到虚拟机硬件关键词: {keyword} in '{combined_vendor_info}'")
                    return True

    except Exception as e:
        print(f"检查硬件制造商时出错: {e}")
        pass

    return False


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
        if system == "Windows":
            board_serial = execute_powershell_command("Get-WmiObject -Class Win32_BaseBoard | Select-Object -ExpandProperty SerialNumber")
            cpu_id = execute_powershell_command("Get-WmiObject -Class Win32_Processor | Select-Object -ExpandProperty ProcessorId")

        elif system == "Linux":
            try:
                with open('/sys/class/dmi/id/board_serial', 'r') as f:
                    board_serial = f.read().strip()
            except Exception:
                try:  # 备用方案，可能需要权限，且某些系统没有dmidecode或没有序列号
                    board_serial = subprocess.check_output('sudo dmidecode -s baseboard-serial-number', shell=True, text=True).strip()
                except Exception as e_bs:
                    print(f"获取Linux主板序列号失败: {e_bs}")

            try:
                # 尝试从 /proc/cpuinfo 获取一个组合的 CPU 标识
                # 注意：这不是一个标准化的 "ProcessorId"，不同架构和内核版本可能不同
                cpu_info_raw = subprocess.check_output('cat /proc/cpuinfo', shell=True, text=True)
                temp_cpu_id_parts = []
                for line in cpu_info_raw.split('\n'):
                    if "vendor_id" in line or "model name" in line or "processor" in line and ":" in line:
                        # 取冒号后的值并去除多余空格
                        part = line.split(':', 1)[1].strip()
                        if part:
                            temp_cpu_id_parts.append(part)
                cpu_id = "-".join(sorted(list(set(temp_cpu_id_parts))))  # 去重并排序组合
            except Exception as e_cpu:
                print(f"获取Linux CPU信息失败: {e_cpu}")

        elif system == "Darwin":  # macOS
            try:
                board_serial = subprocess.check_output("ioreg -l | grep IOPlatformSerialNumber", shell=True, text=True).split('"')[
                    3
                ]  # IOPlatformSerialNumber = "THIS_VALUE"
            except Exception as e_bs_mac:
                print(f"获取macOS主板序列号失败: {e_bs_mac}")

            # macOS 不容易获取稳定的CPU ID，主板序列号通常足够唯一
            # 如果确实需要，可以尝试 system_profiler SPHardwareDataType | grep "Processor Name" 等
            # 但这里我们为了稳定性，如果board_serial获取到了，可以用它的一部分或全部作为cpu_id的补充
            cpu_id = board_serial  # 简单复用，或保持为空如果board_serial也没有

        # 获取所有物理网卡的MAC地址 (使用psutil跨平台)
        try:
            for interface, addrs in psutil.net_if_addrs().items():
                is_loopback = getattr(psutil.net_if_stats().get(interface, object()), 'isup', False) and interface.lower().startswith('lo')
                if is_loopback:
                    continue

                for addr in addrs:
                    if addr.family == psutil.AF_LINK:  # AF_LINK 通常表示MAC地址
                        mac_addresses.append(addr.address.upper())
            mac_addresses.sort()  # 排序以保证顺序一致性
        except Exception as e_mac:
            print(f"获取MAC地址时出错: {e_mac}")

    except Exception as e:
        print(f"[警告] 获取硬件信息时发生意外错误: {e}。哈希可能不够准确。")

    combined_string = f"BOARD:{board_serial}-CPU:{cpu_id}-MACS:{''.join(mac_addresses)}"
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

    def login(self, order_id: str, code: str, check_method: str = "1"):
        try:
            # 使用身份验证器App
            response = httpx.post(
                f"{self.base_url}/order/auth/login",
                json={"order_id": order_id, "code": code, "device_hash": self.device_hash, "check_method": int(check_method)},
            )
            return response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]错误: 无法连接到服务器。 {e}[/]")
            return None

    def send_email_code(self, email: str):
        """发送邮箱验证码"""
        try:
            response = httpx.post(f"{self.base_url}/auth/send-email-code", json={"email": email, "tool_code": self.tool_code})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            console.print(f"[bold red]错误: {e.response.json()['detail']}[/]")
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
        check_method = Prompt.ask(
            "请选择验证方式: \n[bold green]1. 使用身份验证器App[/] \n2. 使用邮箱动态验证码",
            choices=["1", "2"],
            default="1",
            show_choices=False,
        )
        if check_method == "2":
            api.send_email_code(decode_token['email'])

        code = Prompt.ask("请输入您身份验证器App上的6位数字码")

        response = api.login(decode_token['order_id'], code, check_method)

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
