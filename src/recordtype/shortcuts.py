def bind_shortcuts(root, on_save, on_mark):
    root.bind("<Control-s>", lambda e: on_save())
    root.bind("<Control-S>", lambda e: on_save())
    root.bind("<Control-m>", lambda e: on_mark())
    root.bind("<Control-M>", lambda e: on_mark())
