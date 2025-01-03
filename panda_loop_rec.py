import math
import os
import threading
import time
import tkinter as tk
from io import BytesIO

import PIL.Image
import librosa
import pyaudio
import pyrubberband as pyrb
import soundfile as sf
import ttkbootstrap as ttk
from PIL import Image, ImageTk
from pydub import AudioSegment
from pydub.playback import play
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg
from ttkbootstrap.toast import ToastNotification


def load_svg(image):
    svg_file = svg2rlg(image)
    bytes_png = BytesIO()
    renderPM.drawToFile(svg_file, bytes_png, bg=0x393A4C, fmt="PNG")

    # Open the PNG with PIL
    bytes_png.seek(0)  # Reset the pointer to the start of the BytesIO object
    img = Image.open(bytes_png).convert("RGBA")  # Convert to RGBA mode

    # Make the background transparent
    datas = img.getdata()
    new_data = []
    for pixel in datas:
        # Change pixels that are not part of the icon to transparent
        if pixel[:3] != (0xff, 0xff, 0xff):
            new_data.append((0xff, 0xff, 0xff, 0))  # Transparent pixel
        else:
            new_data.append(pixel)  # Keep other pixels unchanged

    img.putdata(new_data)

    return ImageTk.PhotoImage(img)


def toast(title, text):
    toast_msg = ToastNotification(
        title=title,
        message=text,
        duration=3000, position=(100, 100, 'ne')
    )
    toast_msg.show_toast()


class PandaLoopRecorder:
    def __init__(self):
        self.progress = 0.0
        self.progress_bar = None
        self.set_config_btn = None
        self.seconds_entry = None
        self.minutes_entry = None
        self.bpm_entry = None
        self.undo_button = None
        self.save_button = None
        self.speed_scale = None
        self.stop_button = None
        self.p = pyaudio.PyAudio()
        self.audio_file = None
        self.current_audio = None
        self.undo_stack = []
        self.recording = False
        self.playing = False
        self.speed = 1.0
        self.record_position = 0
        self.playback_start_time = None
        self.clip_length = None
        self.bpm = 80
        self.speed_scale_label = None
        self.play_button = None
        self.record_button = None

    def calculate_clip_length(self, bpm, minutes, seconds):
        beats_per_second = bpm / 60
        total_seconds = minutes * 60 + seconds
        bars = math.ceil((total_seconds * beats_per_second) / 4)
        return bars * 4 / beats_per_second

    def configure_audio(self, bpm, minutes, seconds):
        try:
            self.clip_length = int(self.calculate_clip_length(bpm, minutes, seconds) * 1000)
            self.audio_file = AudioSegment.silent(duration=self.clip_length)
            self.current_audio = self.audio_file
            self.undo_stack.clear()
            toast('Success', 'Audio configuration set. You can now play or record.')
            print(f"Clip length: {self.clip_length}")

            # Enable audio playback buttons
            self.play_button.config(state='normal')
            self.record_button.config(state='normal')
            self.stop_button.config(state='normal')
            self.speed_scale.config(state='normal')
            self.save_button.config(state='normal')
            self.undo_button.config(state='normal')

            # Disable audio configuration options
            self.bpm_entry.config(state=tk.DISABLED)
            self.minutes_entry.config(state=tk.DISABLED)
            self.seconds_entry.config(state=tk.DISABLED)
            self.set_config_btn.config(state=tk.DISABLED)

        except ValueError:
            toast("Invalid Input", "Please enter valid numbers for BPM, minutes, and seconds.")

    def on_configure(self):
        self.bpm = int(self.bpm_entry.get())
        minutes = int(self.minutes_entry.get())
        seconds = int(self.seconds_entry.get())
        self.configure_audio(self.bpm, minutes, seconds)

    def play_audio(self):
        if not self.current_audio:
            toast('Warning', 'No audio to play.')
            return

        while self.playing:
            print("while loop")
            self.current_audio.export("temp_1.wav", format="wav")
            y, sr = librosa.load("temp_1.wav", sr=None)
            y_stretched = pyrb.time_stretch(y, sr, self.speed)
            print(self.speed)
            sf.write("temp_2.wav", y_stretched, sr, format='wav')

            playback_audio = AudioSegment.from_wav("temp_2.wav")
            os.unlink("temp_1.wav")
            os.unlink("temp_2.wav")

            self.playback_start_time = time.time()
            print(f"play start time: {self.playback_start_time}, playback length: {len(playback_audio)}")
            def do_play():
                play(playback_audio)
            threading.Thread(target=do_play).start()
            print(f"after play: {time.time()}")

            for time_chunk in range(0, len(playback_audio), 10):
                self.progress = float(time_chunk) / float(len(playback_audio))
                self.progress_bar.config(value=int(self.progress * 100.0))
                time.sleep(1/100)
            print(f"after sleep: {time.time()}")
            # time.sleep(len(playback_audio) / 1000)

    def start_play(self):
        if not self.audio_file:
            toast('Warning', 'Configure audio first.')
            return

        if self.playing:
            toast('Warning', 'Already playing audio!')
            return

        self.playing = True
        self.play_button.config(style="success.TButton")
        print("Playing audio")

        play_thread = threading.Thread(target=self.play_audio, daemon=True)
        play_thread.start()

    def stop(self):
        self.playing = False
        self.play_button.config(style="info.TButton")
        self.recording = False
        self.record_button.config(style="warning.TButton")
        self.playback_start_time = None

    def start_record(self):
        if not self.playing:
            toast("Warning", "Play the audio before recording.")
            return

        if self.recording:
            toast("Success", "Stopped recording audio.")
            self.recording = False
            self.record_button.config(style="warning.TButton")
            return

        toast("Information", "Started recording.")
        self.recording = True
        self.record_button.config(style="danger.TButton")
        self.undo_stack.append(self.current_audio[:])

        record_thread = threading.Thread(target=self.record, daemon=True)
        record_thread.start()

    def record(self):
        # Logic for overdubbing
        try:
            # Initialize audio input stream
            stream = self.p.open(format=pyaudio.paInt16,
                                 channels=1,
                                 rate=44100,
                                 input=True,
                                 frames_per_buffer=1024)

            # Record audio and overdub
            new_frames = []
            while self.recording:
                data = stream.read(1024)
                new_frames.append(data)

            stream.stop_stream()
            stream.close()

            # Convert recorded frames to AudioSegment
            new_audio = AudioSegment(
                data=b"".join(new_frames),
                sample_width=2,
                frame_rate=44100,
                channels=1
            )

            # Overdub the new audio onto the current audio
            co = self.current_audio[:]
            current_len = len(co)
            target_position = int(current_len * self.progress)
            max_len = max(current_len, target_position + len(new_audio))
            print(current_len, target_position, "max_len", max_len, "new", len(new_audio))
            silent_audio = AudioSegment.silent(duration=max_len)
            overlay_orig = silent_audio.overlay(co, loop=False)
            self.current_audio = overlay_orig.overlay(new_audio, position=target_position, loop=False)

        except Exception as e:
            toast("Error", f"Recording failed: {e}")

    def save_audio(self):
        if not self.current_audio:
            toast("Warning", "No audio to save.")
            return
        self.current_audio.export("output.wav", format="wav")
        toast("Saved", "Audio saved as output.wav")

    def undo(self):
        if self.undo_stack:
            self.current_audio = self.undo_stack.pop()
            toast("Undo", "Undo successful.")
        else:
            toast("Warning", "Nothing to undo.")

    def adjust_speed(self, value):
        new_speed = float(value)
        if new_speed >= 0:
            self.speed = new_speed + 1
        else:
            self.speed = -1 / (new_speed - 1)

        # Change speed label to show new speed
        self.speed_scale_label.config(text=f"Speed: {self.speed:.2f}x")

    def main_window(self):
        root = tk.Tk()
        style = ttk.Style("lumen")

        root.title("Tape Loop Recorder")

        # Top row (row 0) - indicator lights

        # Row 1
        # Control buttons
        play_btn_img = load_svg('assets/images/play-fill.svg')
        stop_btn_img = load_svg('assets/images/stop-fill.svg')
        record_btn_img = load_svg('assets/images/record-fill.svg')
        save_btn_img = load_svg('assets/images/floppy2-fill.svg')
        undo_btn_img = load_svg('assets/images/undo-left-round-square-svgrepo-com.svg')

        # Play button
        self.play_button = ttk.Button(root, text="Play️", command=self.start_play, image=play_btn_img,
                                      style="info.TButton", state=tk.DISABLED)
        self.play_button.grid(row=1, column=0, padx=5, pady=5)

        # Stop button
        self.stop_button = ttk.Button(root, text="Stop", command=self.stop, image=stop_btn_img,
                                      style="dark", state=tk.DISABLED)
        self.stop_button.grid(row=1, column=1, padx=5, pady=5)

        # Record button
        self.record_button = ttk.Button(root, text="Record", command=self.start_record, image=record_btn_img,
                                        style="warning.TButton", state=tk.DISABLED)
        self.record_button.grid(row=1, column=2, padx=5, pady=5)

        # Speed adjustment slider
        self.speed_scale_label = ttk.Label(root, text="Speed: 1.00x")
        self.speed_scale_label.grid(row=1, column=3, padx=5, pady=5)
        self.speed_scale = ttk.Scale(root, from_=-5.0, to=5.0, value=0, orient=tk.HORIZONTAL,
                                     command=self.adjust_speed, state=tk.DISABLED)
        self.speed_scale.grid(row=1, column=4, columnspan=2, padx=5, pady=5)

        # Save button
        self.save_button = ttk.Button(root, text="Save", command=self.save_audio, image=save_btn_img,
                                      style="dark", state=tk.DISABLED)
        self.save_button.grid(row=1, column=6, padx=5, pady=5)

        # Undo button
        self.undo_button = ttk.Button(root, text="Undo", command=self.undo, image=undo_btn_img,
                                      style="dark", state=tk.DISABLED)
        self.undo_button.grid(row=1, column=7, padx=5, pady=5)

        # Row 2
        # Progress bar
        self.progress_bar = ttk.Progressbar(root, value=0, style='success.Striped.Horizontal.TProgressbar', length=500)
        self.progress_bar.grid(row=2, column=0, padx=5, pady=5, columnspan=8)

        # Row 3
        # Configuration section
        # BPM
        ttk.Label(root, text="BPM:").grid(row=3, column=0, padx=5, pady=5)
        bpm_default_value = tk.DoubleVar(value=80)
        self.bpm_entry = ttk.Entry(root, textvariable=bpm_default_value, width=5)
        self.bpm_entry.grid(row=3, column=1, padx=5, pady=5)

        # Minutes
        ttk.Label(root, text="Minutes:").grid(row=3, column=2, padx=5, pady=5)
        minutes_default_value = tk.DoubleVar(value=0)
        self.minutes_entry = ttk.Entry(root, textvariable=minutes_default_value, width=5)
        self.minutes_entry.grid(row=3, column=3, padx=5, pady=5)

        # Seconds
        ttk.Label(root, text="Seconds:").grid(row=3, column=4, padx=5, pady=5)
        seconds_default_value = tk.DoubleVar(value=10)
        self.seconds_entry = ttk.Entry(root, textvariable=seconds_default_value, width=5)
        self.seconds_entry.grid(row=3, column=5, padx=5, pady=5)

        # Button
        self.set_config_btn = ttk.Button(root, text="Set Configuration", command=self.on_configure)
        self.set_config_btn.grid(row=3, column=6, columnspan=2, pady=10)

        root.mainloop()


if __name__ == "__main__":
    app = PandaLoopRecorder()
    app.main_window()
