import numpy as np
import scipy.io.wavfile as wav
import threading
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

try:
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except Exception:
    AUDIO_AVAILABLE = False

# ─────────────────────────────────────────────
# SIGNAL PARAMETERS
# ─────────────────────────────────────────────
FS        = 44100
TONE_DUR  = 0.040
GAP_DUR   = 0.010
THRESHOLD = 0.04
DEBOUNCE  = 1

N_TONE = int(FS * TONE_DUR)
N_GAP  = int(FS * GAP_DUR)

# ─────────────────────────────────────────────
# CHARACTER → FREQUENCY MAP
# ─────────────────────────────────────────────
TURKISH_DISPLAY = [
    ' ', 'A', 'B', 'C', 'Ç', 'D', 'E', 'F', 'G', 'Ğ',
    'H', 'I', 'İ', 'J', 'K', 'L', 'M', 'N', 'O', 'Ö',
    'P', 'R', 'S', 'Ş', 'T', 'U', 'Ü', 'V', 'Y', 'Z'
]
LOW_FREQS  = [700, 770, 852, 941, 1040, 1100]
HIGH_FREQS = [1209, 1336, 1477, 1633, 1750]

CHAR_TO_FREQ = {}
FREQ_TO_CHAR = {}
for idx, ch in enumerate(TURKISH_DISPLAY):
    fl = LOW_FREQS[idx // 5]
    fh = HIGH_FREQS[idx % 5]
    CHAR_TO_FREQ[ch] = (fl, fh)
    FREQ_TO_CHAR[(fl, fh)] = ch

# ─────────────────────────────────────────────
# CODEC CORE
# ─────────────────────────────────────────────
def synthesize_tone(fl, fh):
    t    = np.arange(N_TONE) / FS
    tone = np.sin(2*np.pi*fl*t) + np.sin(2*np.pi*fh*t)
    tone = tone / np.max(np.abs(tone))
    return (tone * np.hanning(N_TONE)).astype(np.float32)

def encode(text, output_path="encoded.wav"):
    text_upper = text.upper()
    gap = np.zeros(N_GAP, dtype=np.float32)
    segments = []
    skipped = []
    for ch in text_upper:
        if ch not in CHAR_TO_FREQ:
            skipped.append(ch)
            continue
        fl, fh = CHAR_TO_FREQ[ch]
        segments.append(synthesize_tone(fl, fh))
        segments.append(gap)
    if not segments:
        raise ValueError("No valid characters to encode.")
    audio = np.concatenate(segments)
    wav.write(output_path, FS, audio)
    return audio, skipped

def goertzel(samples, freq, fs):
    N = len(samples)
    k = int(round(N * freq / fs))
    omega = 2 * np.pi * k / N
    coeff = 2 * np.cos(omega)
    s0 = s1 = s2 = 0.0
    for x in samples:
        s0 = x + coeff*s1 - s2
        s2 = s1; s1 = s0
    power = s1**2 + s2**2 - coeff*s1*s2
    return np.sqrt(power) / N

def decode(wav_path="encoded.wav"):
    fs_file, audio = wav.read(wav_path)
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max
    all_freqs = sorted(set(LOW_FREQS + HIGH_FREQS))
    hann_win  = np.hanning(N_TONE)
    step      = N_TONE + N_GAP
    decoded = []; prev_char = None; consec = 0; pos = 0
    all_mags = []
    while pos + N_TONE <= len(audio):
        frame = audio[pos:pos+N_TONE] * hann_win
        mags  = {f: goertzel(frame, f, FS) for f in all_freqs}
        lm    = {f: mags[f] for f in LOW_FREQS}
        hm    = {f: mags[f] for f in HIGH_FREQS}
        bl    = max(lm, key=lm.get)
        bh    = max(hm, key=hm.get)
        all_mags.append(mags)
        if lm[bl] > THRESHOLD and hm[bh] > THRESHOLD:
            char = FREQ_TO_CHAR.get((bl, bh))
            if char:
                if char == prev_char: consec += 1
                else: consec = 1; prev_char = char
                if consec == DEBOUNCE: decoded.append(char)
            else: prev_char = None; consec = 0
        else: prev_char = None; consec = 0
        pos += step
    return ''.join(decoded), audio, all_mags

# ─────────────────────────────────────────────
# GUI APPLICATION
# ─────────────────────────────────────────────
DARK_BG   = "#1a1a2e"
PANEL_BG  = "#16213e"
ACCENT    = "#0f3460"
HIGHLIGHT = "#e94560"
TEXT_CLR  = "#eaeaea"
ENTRY_BG  = "#0d1b2a"
GREEN     = "#4ecca3"
FONT_MAIN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 10)
FONT_H1   = ("Segoe UI", 14, "bold")
FONT_H2   = ("Segoe UI", 11, "bold")

WAV_FILE  = "encoded.wav"

class DTMFApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("COE 216 — DTMF Text Codec  |  Group 9")
        self.geometry("1150x750")
        self.minsize(900, 600)
        self.configure(bg=DARK_BG)
        self._audio = None
        self._build_ui()

    # ── UI CONSTRUCTION ──────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=ACCENT, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="DTMF Text Codec", font=("Segoe UI", 18, "bold"),
                 bg=ACCENT, fg=TEXT_CLR).pack()
        tk.Label(hdr, text="COE 216 — Signals and Systems  |  Group 9",
                 font=("Segoe UI", 9), bg=ACCENT, fg="#aaaacc").pack()

        # Main layout: left panel + right canvas
        main = tk.Frame(self, bg=DARK_BG)
        main.pack(fill="both", expand=True, padx=12, pady=10)

        left  = tk.Frame(main, bg=DARK_BG, width=340)
        left.pack(side="left", fill="y", padx=(0,10))
        left.pack_propagate(False)

        right = tk.Frame(main, bg=PANEL_BG, bd=1, relief="flat")
        right.pack(side="left", fill="both", expand=True)

        self._build_left(left)
        self._build_plots(right)

    def _build_left(self, parent):
        def section(p, title):
            f = tk.LabelFrame(p, text=title, bg=DARK_BG, fg=GREEN,
                              font=FONT_BOLD, bd=1, relief="groove",
                              labelanchor="n", padx=10, pady=8)
            f.pack(fill="x", pady=(0, 10))
            return f

        # ── ENCODE ──
        enc_f = section(parent, "  ENCODE  ")

        tk.Label(enc_f, text="Enter Turkish text:", bg=DARK_BG,
                 fg=TEXT_CLR, font=FONT_MAIN).pack(anchor="w")
        self.input_var = tk.StringVar()
        self.entry = tk.Entry(enc_f, textvariable=self.input_var, font=FONT_MONO,
                              bg=ENTRY_BG, fg=TEXT_CLR, insertbackground=GREEN,
                              relief="flat", bd=4)
        self.entry.pack(fill="x", pady=(4, 8))
        self.entry.bind("<Return>", lambda e: self._on_encode())
        self.after(100, self.entry.focus_set)

        # Character keyboard
        kb_frame = tk.Frame(enc_f, bg=DARK_BG)
        kb_frame.pack(fill="x", pady=(0,8))
        chars = TURKISH_DISPLAY[1:]  # exclude space, add manually
        cols = 10
        for i, ch in enumerate(chars):
            btn = tk.Button(kb_frame, text=ch, width=3, font=("Segoe UI", 9),
                            bg=ACCENT, fg=TEXT_CLR, activebackground=HIGHLIGHT,
                            activeforeground="white", relief="flat", bd=0,
                            command=lambda c=ch: self._insert_char(c))
            btn.grid(row=i//cols, column=i%cols, padx=1, pady=1)
        # Space & backspace
        ctrl = tk.Frame(enc_f, bg=DARK_BG)
        ctrl.pack(fill="x", pady=(2, 0))
        tk.Button(ctrl, text="SPACE", font=("Segoe UI", 9),
                  bg=ACCENT, fg=TEXT_CLR, activebackground=HIGHLIGHT,
                  relief="flat", bd=0, command=lambda: self._insert_char(' ')
                  ).pack(side="left", expand=True, fill="x", padx=(0,2))
        tk.Button(ctrl, text="⌫ DEL", font=("Segoe UI", 9),
                  bg="#3a1a2e", fg=TEXT_CLR, activebackground=HIGHLIGHT,
                  relief="flat", bd=0, command=self._backspace
                  ).pack(side="left", expand=True, fill="x")

        btn_enc = tk.Button(enc_f, text="▶  ENCODE & PLAY",
                            font=FONT_BOLD, bg=HIGHLIGHT, fg="white",
                            activebackground="#c73652", relief="flat",
                            bd=0, pady=8, command=self._on_encode)
        btn_enc.pack(fill="x", pady=(10,0))

        # ── DECODE ──
        dec_f = section(parent, "  DECODE  ")

        btn_dec = tk.Button(dec_f, text="⟳  DECODE FROM encoded.wav",
                            font=FONT_BOLD, bg=GREEN, fg=DARK_BG,
                            activebackground="#3ab89a", relief="flat",
                            bd=0, pady=8, command=self._on_decode)
        btn_dec.pack(fill="x")

        tk.Button(dec_f, text="📂  Load WAV File…",
                  font=FONT_MAIN, bg=ACCENT, fg=TEXT_CLR,
                  activebackground=HIGHLIGHT, relief="flat",
                  bd=0, pady=6, command=self._load_wav
                  ).pack(fill="x", pady=(6,0))

        # ── RESULT ──
        res_f = section(parent, "  RESULT  ")
        self.result_text = tk.Text(res_f, height=5, font=FONT_MONO,
                                   bg=ENTRY_BG, fg=GREEN, insertbackground=GREEN,
                                   relief="flat", bd=4, wrap="word", state="disabled")
        self.result_text.pack(fill="both", expand=True)

        # ── STATUS ──
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(parent, textvariable=self.status_var, bg=DARK_BG,
                 fg="#aaaacc", font=("Segoe UI", 9), anchor="w",
                 wraplength=310).pack(fill="x", pady=(4,0))

    def _build_plots(self, parent):
        tk.Label(parent, text="Signal Analysis", font=FONT_H2,
                 bg=PANEL_BG, fg=GREEN).pack(pady=(8,2))

        self.fig = Figure(figsize=(6, 8), facecolor="#0d1b2a")
        self.ax_wave = self.fig.add_subplot(3, 1, 1)
        self.ax_fft  = self.fig.add_subplot(3, 1, 2)
        self.ax_goer = self.fig.add_subplot(3, 1, 3)
        self.fig.tight_layout(pad=2.5)

        for ax in [self.ax_wave, self.ax_fft, self.ax_goer]:
            ax.set_facecolor("#0d1b2a")
            ax.tick_params(colors="#aaaacc", labelsize=7)
            for spine in ax.spines.values():
                spine.set_edgecolor("#333355")

        self._init_plot_texts()

        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)

    def _init_plot_texts(self):
        for ax, title in [(self.ax_wave, "Waveform"),
                          (self.ax_fft,  "FFT Spectrum"),
                          (self.ax_goer, "Goertzel Magnitudes")]:
            ax.clear()
            ax.set_facecolor("#0d1b2a")
            ax.text(0.5, 0.5, "Press ENCODE or DECODE…",
                    ha="center", va="center", color="#555577",
                    fontsize=9, transform=ax.transAxes)
            ax.set_title(title, color="#aaaacc", fontsize=8, pad=4)
            ax.tick_params(colors="#aaaacc", labelsize=7)
            for sp in ax.spines.values():
                sp.set_edgecolor("#333355")

    # ── HELPERS ──────────────────────────────
    def _insert_char(self, ch):
        # Insert at cursor position, then return focus to entry
        self.entry.insert(tk.INSERT, ch)
        self.entry.focus_set()

    def _backspace(self):
        # Delete char before cursor, then return focus to entry
        try:
            self.entry.delete(tk.INSERT + "-1c", tk.INSERT)
        except tk.TclError:
            v = self.input_var.get()
            if v:
                self.input_var.set(v[:-1])
        self.entry.focus_set()

    def _set_result(self, text):
        self.result_text.config(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("end", text)
        self.result_text.config(state="disabled")

    def _set_status(self, msg, color="#aaaacc"):
        self.status_var.set(msg)

    # ── ENCODE ───────────────────────────────
    def _on_encode(self):
        text = self.input_var.get().strip()
        if not text:
            messagebox.showwarning("Empty Input", "Please enter some text to encode.")
            return
        self._set_status("Encoding…")
        self.update_idletasks()
        threading.Thread(target=self._encode_thread, args=(text,), daemon=True).start()

    def _encode_thread(self, text):
        try:
            audio, skipped = encode(text, WAV_FILE)
            self._audio = audio
            duration = len(audio) / FS
            msg = "Encoded: '{}'\n({} chars, {:.3f} s)".format(
                text.upper(), len([c for c in text.upper() if c in CHAR_TO_FREQ]), duration)
            if skipped:
                msg += "\nSkipped: {}".format(skipped)
            self.after(0, self._set_result, msg)
            self.after(0, self._update_plots_encode, audio, text.upper())
            self.after(0, self._set_status, "Encoded successfully. Playing audio…")

            if AUDIO_AVAILABLE:
                sd.play(audio, samplerate=FS)
                sd.wait()
                self.after(0, self._set_status, "Playback complete.")
            else:
                self.after(0, self._set_status,
                           "Encoded. (sounddevice unavailable — no playback)")
        except Exception as e:
            self.after(0, messagebox.showerror, "Encode Error", str(e))
            self.after(0, self._set_status, "Error: {}".format(e))

    def _update_plots_encode(self, audio, text):
        # ── Waveform (first 80 ms) ──
        ax = self.ax_wave
        ax.clear(); ax.set_facecolor("#0d1b2a")
        n_show = min(len(audio), int(FS * 0.08))
        t = np.arange(n_show) / FS * 1000  # ms
        ax.plot(t, audio[:n_show], color=HIGHLIGHT, lw=0.6, alpha=0.9)
        ax.set_title("Encoded Waveform (first 80 ms) — \"{}\"".format(text[:20]),
                     color="#aaaacc", fontsize=8, pad=4)
        ax.set_xlabel("Time (ms)", color="#aaaacc", fontsize=7)
        ax.set_ylabel("Amplitude", color="#aaaacc", fontsize=7)
        ax.tick_params(colors="#aaaacc", labelsize=7)
        for sp in ax.spines.values(): sp.set_edgecolor("#333355")

        # ── FFT of first character ──
        ax = self.ax_fft
        ax.clear(); ax.set_facecolor("#0d1b2a")
        frame = audio[:N_TONE] * np.hanning(N_TONE)
        N = len(frame)
        fft_mag = np.abs(np.fft.rfft(frame)) / N
        freqs   = np.fft.rfftfreq(N, 1/FS)
        ax.plot(freqs, fft_mag, color="#4fc3f7", lw=0.8)
        ax.set_xlim(0, 2200)
        # Mark the expected peaks for first character
        first_ch = next((c for c in text if c in CHAR_TO_FREQ), None)
        if first_ch:
            fl, fh = CHAR_TO_FREQ[first_ch]
            ax.axvline(fl, color=GREEN, lw=1.2, linestyle="--",
                       label="f_low={} Hz".format(fl))
            ax.axvline(fh, color=HIGHLIGHT, lw=1.2, linestyle="--",
                       label="f_high={} Hz".format(fh))
            ax.legend(fontsize=7, facecolor="#0d1b2a", labelcolor=TEXT_CLR,
                      edgecolor="#333355")
        ax.set_title("FFT Spectrum — First Character: '{}'".format(first_ch or "?"),
                     color="#aaaacc", fontsize=8, pad=4)
        ax.set_xlabel("Frequency (Hz)", color="#aaaacc", fontsize=7)
        ax.set_ylabel("Magnitude", color="#aaaacc", fontsize=7)
        ax.tick_params(colors="#aaaacc", labelsize=7)
        for sp in ax.spines.values(): sp.set_edgecolor("#333355")

        # ── Goertzel bars for first character ──
        ax = self.ax_goer
        ax.clear(); ax.set_facecolor("#0d1b2a")
        all_f = sorted(set(LOW_FREQS + HIGH_FREQS))
        mags  = [goertzel(frame, f, FS) for f in all_f]
        clrs  = []
        first_ch = next((c for c in text if c in CHAR_TO_FREQ), None)
        fl_exp, fh_exp = CHAR_TO_FREQ.get(first_ch, (None, None)) if first_ch else (None, None)
        for f in all_f:
            if f == fl_exp: clrs.append(GREEN)
            elif f == fh_exp: clrs.append(HIGHLIGHT)
            else: clrs.append("#4444aa")
        bars = ax.bar([str(f) for f in all_f], mags, color=clrs, width=0.7)
        ax.axhline(THRESHOLD, color="yellow", lw=1, linestyle=":", label="Threshold")
        ax.legend(fontsize=7, facecolor="#0d1b2a", labelcolor=TEXT_CLR,
                  edgecolor="#333355")
        ax.set_title("Goertzel Magnitudes — First Character: '{}'".format(first_ch or "?"),
                     color="#aaaacc", fontsize=8, pad=4)
        ax.set_xlabel("Frequency (Hz)", color="#aaaacc", fontsize=7)
        ax.set_ylabel("Normalised Magnitude", color="#aaaacc", fontsize=7)
        ax.tick_params(axis='x', rotation=45, colors="#aaaacc", labelsize=6.5)
        ax.tick_params(axis='y', colors="#aaaacc", labelsize=7)
        for sp in ax.spines.values(): sp.set_edgecolor("#333355")

        self.fig.tight_layout(pad=2.5)
        self.canvas.draw()

    # ── DECODE ───────────────────────────────
    def _on_decode(self):
        if not os.path.exists(WAV_FILE):
            messagebox.showwarning("No File", "encoded.wav not found. Please encode first.")
            return
        self._set_status("Decoding…")
        self.update_idletasks()
        threading.Thread(target=self._decode_thread, args=(WAV_FILE,), daemon=True).start()

    def _load_wav(self):
        path = filedialog.askopenfilename(
            title="Select WAV file", filetypes=[("WAV files", "*.wav"), ("All", "*.*")])
        if path:
            self._set_status("Decoding {}…".format(os.path.basename(path)))
            threading.Thread(target=self._decode_thread, args=(path,), daemon=True).start()

    def _decode_thread(self, path):
        try:
            result, audio, all_mags = decode(path)
            msg = "Decoded text:\n{}".format(result if result else "(nothing detected)")
            self.after(0, self._set_result, msg)
            self.after(0, self._update_plots_decode, audio, result, all_mags)
            self.after(0, self._set_status,
                       "Decoded: {} character(s) found.".format(len(result)))
        except Exception as e:
            self.after(0, messagebox.showerror, "Decode Error", str(e))
            self.after(0, self._set_status, "Error: {}".format(e))

    def _update_plots_decode(self, audio, result, all_mags):
        # ── Full waveform ──
        ax = self.ax_wave
        ax.clear(); ax.set_facecolor("#0d1b2a")
        t = np.arange(len(audio)) / FS * 1000
        ax.plot(t, audio, color=HIGHLIGHT, lw=0.4, alpha=0.85)
        ax.set_title("Full Decoded Waveform — \"{}\"".format(result[:30]),
                     color="#aaaacc", fontsize=8, pad=4)
        ax.set_xlabel("Time (ms)", color="#aaaacc", fontsize=7)
        ax.set_ylabel("Amplitude", color="#aaaacc", fontsize=7)
        ax.tick_params(colors="#aaaacc", labelsize=7)
        for sp in ax.spines.values(): sp.set_edgecolor("#333355")

        # ── FFT of full signal ──
        ax = self.ax_fft
        ax.clear(); ax.set_facecolor("#0d1b2a")
        N   = len(audio)
        fft_mag = np.abs(np.fft.rfft(audio)) / N
        freqs   = np.fft.rfftfreq(N, 1/FS)
        ax.plot(freqs, fft_mag, color="#4fc3f7", lw=0.6)
        ax.set_xlim(0, 2200)
        for fl in LOW_FREQS:
            ax.axvline(fl, color=GREEN, lw=0.6, alpha=0.5, linestyle=":")
        for fh in HIGH_FREQS:
            ax.axvline(fh, color=HIGHLIGHT, lw=0.6, alpha=0.5, linestyle=":")
        ax.set_title("FFT Spectrum — Full Signal", color="#aaaacc", fontsize=8, pad=4)
        ax.set_xlabel("Frequency (Hz)", color="#aaaacc", fontsize=7)
        ax.set_ylabel("Magnitude", color="#aaaacc", fontsize=7)
        ax.tick_params(colors="#aaaacc", labelsize=7)
        for sp in ax.spines.values(): sp.set_edgecolor("#333355")

        # ── Average Goertzel magnitudes across all frames ──
        ax = self.ax_goer
        ax.clear(); ax.set_facecolor("#0d1b2a")
        if all_mags:
            all_f   = sorted(set(LOW_FREQS + HIGH_FREQS))
            avg_mag = [np.mean([m[f] for m in all_mags]) for f in all_f]
            clrs    = [GREEN if f in LOW_FREQS else HIGHLIGHT for f in all_f]
            ax.bar([str(f) for f in all_f], avg_mag, color=clrs, width=0.7)
            ax.axhline(THRESHOLD, color="yellow", lw=1, linestyle=":", label="Threshold")
            ax.legend(fontsize=7, facecolor="#0d1b2a", labelcolor=TEXT_CLR,
                      edgecolor="#333355")
        ax.set_title("Average Goertzel Magnitudes — All Frames",
                     color="#aaaacc", fontsize=8, pad=4)
        ax.set_xlabel("Frequency (Hz)", color="#aaaacc", fontsize=7)
        ax.set_ylabel("Normalised Magnitude", color="#aaaacc", fontsize=7)
        ax.tick_params(axis='x', rotation=45, colors="#aaaacc", labelsize=6.5)
        ax.tick_params(axis='y', colors="#aaaacc", labelsize=7)
        for sp in ax.spines.values(): sp.set_edgecolor("#333355")

        self.fig.tight_layout(pad=2.5)
        self.canvas.draw()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    app = DTMFApp()
    app.mainloop()
