## 打包命令

记得修改 --product-name和 --windows-icon-from-ico=.\scripts\key_ghost\fav.ico

```powershell

nuitka --mingw64 --standalone --lto=no --enable-plugin=pyside6 --enable-plugin=upx --upx-binary=C:\\Users\\Kris\\WorkSpace\\upx-5.0.1-win64 --show-progress --output-dir=dist --remove-output --onefile --company-name="toputils.Inc" --product-name="key_dasgjkhasdiughasgh" --product-version="1.0.0" --windows-console-mode="hide" --windows-icon-from-ico=.\scripts\key_ghost\fav.ico main_gui.py

```

# 新增脚本在client_qt/scripts里面新建一个文件夹
你的脚本里面必须定义 **WIN_TITLE**(窗口标题) **TOOL_CODE**(工具代码) 还需要把主窗口定义为MainAppPage
```
class MainAppPage(QWidget):
    authorization_required = Signal() # 登录信号
    script_started = Signal()         # 脚本启动/暂停信号
    script_stopped = Signal()

    # 【步骤1】定义用于热键的专属信号
    hotkey_start_pressed = Signal()   # 快捷键信号
    hotkey_stop_pressed = Signal()

    def __init__(self, email: str, api_client_instance: ApiClient, thread_pool_instance):
        super().__init__()
        self.user_email = email       # 展示订阅信息
        self.api = api_client_instance # 用于访问服务器api
        self.thread_pool = thread_pool_instance  # 计时器和日志线程池
```