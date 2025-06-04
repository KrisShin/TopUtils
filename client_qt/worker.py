# worker.py
from PySide6.QtCore import QObject, Signal, Slot, QRunnable

class WorkerSignals(QObject):
    """定义工作线程可发出的信号"""
    finished = Signal()
    error = Signal(str)
    result = Signal(object)

class Worker(QRunnable):
    """
    通用工作线程，可运行任何函数并发出信号
    """
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            self.signals.error.emit(str(e))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()