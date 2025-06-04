import hashlib
import os
import platform
import subprocess
from PySide6.QtGui import QPixmap, QImage

import psutil
from PIL import Image


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
