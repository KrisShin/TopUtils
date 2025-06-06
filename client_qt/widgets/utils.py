import hashlib
import os
import platform
import subprocess
from PySide6.QtGui import QPixmap, QImage

import psutil
from PIL import Image


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
            
            try:
                mac_addresses_str = execute_powershell_command(
                    "Get-NetAdapter -Physical | Select-Object -ExpandProperty MacAddress"
                )
                if mac_addresses_str:
                    mac_addresses = sorted([addr.replace('-', '').upper() for addr in mac_addresses_str.split()])
            except Exception as e_mac_win:
                print(f"在 Windows 上通过 PowerShell 获取物理 MAC 地址时出错: {e_mac_win}")

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
            # 仍然使用 psutil 获取 MAC 地址，但可以增加过滤
            try:
                for interface, addrs in psutil.net_if_addrs().items():
                    # 过滤掉 loopback 和虚拟接口 (如 veth, docker)
                    if interface.lower().startswith(('lo', 'veth', 'docker')):
                        continue
                    # 尝试检查是否是虚拟设备（更可靠的方法）
                    if 'virtual' in os.path.realpath(f'/sys/class/net/{interface}'):
                        continue
                    for addr in addrs:
                        if addr.family == psutil.AF_LINK:
                            mac_addresses.append(addr.address.upper())
                mac_addresses.sort()
            except Exception as e_mac_linux:
                print(f"在 Linux 上获取 MAC 地址时出错: {e_mac_linux}")
        
        else: # macOS 和其他系统
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
            try:
                for interface, addrs in psutil.net_if_addrs().items():
                    is_loopback = getattr(psutil.net_if_stats().get(interface, object()), 'isup', False) and interface.lower().startswith('lo')
                    if is_loopback:
                        continue
                    for addr in addrs:
                        if addr.family == psutil.AF_LINK:
                            mac_addresses.append(addr.address.upper())
                mac_addresses.sort()
            except Exception as e_mac:
                print(f"获取MAC地址时出错: {e_mac}")

    except Exception as e:
        print(f"[警告] 获取硬件信息时发生意外错误: {e}。哈希可能不够准确。")

    # 使用排序后的稳定信息生成哈希
    combined_string = f"BOARD:{board_serial}-CPU:{cpu_id}-MACS:{''.join(mac_addresses)}"
    final_hash = hashlib.sha256(combined_string.encode()).hexdigest()
    return final_hash


def pil_to_qpixmap(pil_image: Image.Image) -> QPixmap:
    # 将 PIL 图像转换为 RGBA 模式（如果不是）
    if pil_image.mode != "RGBA":
        pil_image = pil_image.convert("RGBA")

    # 获取图像数据
    data = pil_image.tobytes("raw", "RGBA")
    width, height = pil_image.size

    # 创建 QImage
    qimage = QImage(data, width, height, QImage.Format_RGBA8888)

    # 转换为 QPixmap
    qpixmap = QPixmap.fromImage(qimage)
    return qpixmap
