# launcher.py —— 打包入口
import tkinter as tk
from src.recordtype.ui import MainWindow

def main():
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()

if __name__ == "__main__":
    main()
