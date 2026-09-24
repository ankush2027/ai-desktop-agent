"""Summon, submit one request, read the result, dismiss. No chat history."""

from queue import Empty, Queue
from threading import Thread
from typing import Protocol

from interaction import InteractionController, InteractionState, Presentation


class InvocationSurface(Protocol):
    def summon(self) -> None: ...
    def dismiss(self) -> None: ...


class InstantSurface:
    def __init__(self, root, *, controller_factory=InteractionController):
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self._updates = Queue()
        self.controller = controller_factory(self._updates.put)
        self._worker = None
        self._closed = False
        self._dismiss_pending = False
        self._state = InteractionState.IDLE
        self._timer = None
        root.title("Personal Agent")
        root.geometry("600x310")
        root.minsize(420, 260)
        root.configure(background="#f4f5f7")
        root.protocol("WM_DELETE_WINDOW", self.dismiss)
        root.bind("<Escape>", lambda event: self.dismiss())

        panel = ttk.Frame(root, padding=20)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="What do you need?", font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        ttk.Label(panel, text="Type a command, or use a configured voice provider.").pack(anchor="w", pady=(4, 12))
        row = ttk.Frame(panel)
        row.pack(fill="x")
        self.entry = ttk.Entry(row, font=("TkDefaultFont", 12))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda event: self.send())
        self.mic = ttk.Button(row, text="Microphone", command=self.listen)
        self.mic.pack(side="left", padx=(8, 4))
        self.send_button = ttk.Button(row, text="Send", command=self.send)
        self.send_button.pack(side="left")

        self.response = tk.Text(panel, height=6, wrap="word", relief="flat", state="disabled",
                                font=("TkDefaultFont", 11), padx=8, pady=8)
        self.response.pack(fill="both", expand=True, pady=12)
        footer = ttk.Frame(panel)
        footer.pack(fill="x")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(footer, textvariable=self.status, wraplength=360).pack(side="left")
        self.read_reply = tk.BooleanVar(value=False)
        self.speech_toggle = ttk.Checkbutton(footer, text="Read reply", variable=self.read_reply)
        self.speech_toggle.pack(side="right")
        ttk.Button(footer, text="Dismiss · Esc", command=self.dismiss).pack(side="right", padx=8)
        self._timer = root.after(40, self._poll)

    def summon(self):
        self.root.deiconify()
        self.root.lift()
        self.entry.focus_set()

    def _start(self, operation, *args):
        if self._closed or (self._worker is not None and self._worker.is_alive()):
            return
        # Keep Tk calls on its creating thread, including reading the checkbox.
        speak = self.read_reply.get()
        self._set_enabled(False)
        self._worker = Thread(target=operation, args=args, kwargs={"speak": speak}, daemon=False)
        self._worker.start()

    def send(self):
        self._start(self.controller.submit_text, self.entry.get())

    def listen(self):
        if self._state == InteractionState.LISTENING:
            self.controller.cancel_listening()
        else:
            self._start(self.controller.submit_voice)

    def _set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for widget in (self.entry, self.mic, self.send_button, self.speech_toggle):
            widget.configure(state=state)

    def _present(self, update: Presentation):
        self._state = update.state
        label = "Ready" if update.state == InteractionState.IDLE else update.state.value
        self.status.set(update.notice or label)
        # Listening/cancellation/provider notices do not replace an existing
        # result. Clear it only once a new text request reaches the core, or
        # replace it when the core supplies the next response.
        if update.response or update.state == InteractionState.PROCESSING:
            self.response.configure(state="normal")
            self.response.delete("1.0", "end")
            self.response.insert("1.0", update.response)
            self.response.configure(state="disabled")
        if update.state == InteractionState.LISTENING:
            self.mic.configure(text="Cancel", state="normal")
        else:
            self.mic.configure(text="Microphone", state="disabled")
        if update.dismiss:
            self.dismiss()

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                update = self._updates.get_nowait()
                if not self._dismiss_pending:
                    self._present(update)
                    if self._closed:
                        return
        except Empty:
            pass
        if self._worker is None or not self._worker.is_alive():
            if self._dismiss_pending:
                self._close()
                return
            self._set_enabled(True)
        if not self._closed:
            self._timer = self.root.after(40, self._poll)

    def dismiss(self):
        if self._closed:
            return
        self.controller.dismiss()
        if self._worker is not None and self._worker.is_alive():
            # Do not kill an in-flight core operation or abandon a database write.
            # Suppress late UI results; the window disappears immediately.
            self._dismiss_pending = True
            self.root.withdraw()
        else:
            self._close()

    def _close(self):
        self._closed = True
        if self._timer is not None:
            self.root.after_cancel(self._timer)
        self.root.destroy()


def main():
    try:
        import tkinter as tk
    except ImportError:
        print("Desktop UI requires Python with Tk support. The text interface is still available: python main.py")
        return 1
    try:
        root = tk.Tk()
    except tk.TclError:
        print("Desktop UI could not open a display. The text interface is still available: python main.py")
        return 1
    surface = InstantSurface(root)
    surface.summon()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
