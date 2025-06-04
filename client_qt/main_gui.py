# main_gui.py
import sys
from PySide6.QtWidgets import QApplication
from main_window import MainWindow
from api_client import ApiClient, BASE_URL

if __name__ == "__main__":
    app = QApplication(sys.argv)

    api_client = ApiClient(BASE_URL)

    window = MainWindow(api_client)
    window.resize(400, 300)
    window.show()

    sys.exit(app.exec())
