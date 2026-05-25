import sys
import math
from collections import deque

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout
from PySide6.QtCore import QTimer

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


class MplCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, max_points=200):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)

        super().__init__(self.fig)

        # Data buffers
        self.max_points = max_points
        self.x_data = deque(maxlen=max_points)
        self.y_data = deque(maxlen=max_points)

        # Initial empty line
        (self.line,) = self.ax.plot([], [])

        self.ax.set_xlabel("t")
        self.ax.set_ylabel("value")
        self.ax.grid(True)

    def append_point(self, x, y):
        """Add one point and update line."""
        self.x_data.append(x)
        self.y_data.append(y)

        self.line.set_data(self.x_data, self.y_data)
        self.ax.relim()
        self.ax.autoscale_view()

        self.draw_idle()   # redraw canvas (non-blocking)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.canvas = MplCanvas(self, max_points=200)

        layout = QVBoxLayout()
        layout.addWidget(self.canvas)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.setWindowTitle("PySide6 + Matplotlib dynamic plot")

        # time variable for demo data
        self.t = 0.0
        self.dt = 0.1

        # QTimer → calls self.on_timer() every 50 ms
        self.timer = QTimer(self)
        self.timer.setInterval(50)   # ms
        self.timer.timeout.connect(self.on_timer)
        self.timer.start()

    def on_timer(self):
        """Timer callback: here you add new data to the plot."""
        # Example: fake data (sine wave)
        y = math.sin(self.t)
        self.canvas.append_point(self.t, y)
        self.t += self.dt


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

