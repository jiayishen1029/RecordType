import tkinter as tk
from .ui import MainWindow

def main():
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()

if __name__ == "__main__":
    main()

