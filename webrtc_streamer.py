import argparse
import asyncio
import fractions
import time
import logging
import queue
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
    RTCIceServer,
    RTCConfiguration,
)
from aiortc.contrib.media import MediaBlackhole
from aiortc.contrib.signaling import BYE, add_signaling_arguments, create_signaling
from aiortc.mediastreams import AudioStreamTrack
from picamera import PiCamera
from picamera.array import PiRGBArray
import pyaudio

logging.basicConfig(level=logging.INFO)

class VideoTransformTrack(VideoStreamTrack):
    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self.raw_capture = PiRGBArray(camera, size=camera.resolution)

    async def recv(self):
        frame = await asynciosleep(1 / self.camera.framerate)
        self.camera.capture(self.raw_capture, "bgr", use_video_port=True)
        img = self.raw_capture.array

        video_frame = VideoFrame.from_ndarray(img, format="bgr24")
        video_frame.pts = int(self.camera.framerate * time.time())
        video_frame.time_base = fractions.Fraction(1, 1000)

        self.raw_capture.truncate(0)

        return video_frame

class AudioTransformTrack(AudioStreamTrack):
    def __init__(self):
        super().__init__()
        self.sample_rate = 48000
        self.channels = 1
        self.frame_size = 20  # milliseconds
        self.samples_per_frame = (self.sample_rate * self.frame_size) // 1000
        self.q = queue.Queue()

        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.samples_per_frame,
            stream_callback=self._callback,
        )

    def _callback(self, in_data, frame_count, time_info, status_flags):
        self.q.put(in_data)
        return (None, pyaudio.paContinue)

    async def recv(self):
        frame = await asyncio.sleep(self.frame_size / 1000)
        data = self.q.get()

        return AudioFrame.from_ndarray(data, channels=self.channels, sample_rate=self.sample_rate)

    def stop(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

async def run(pc, signaling, camera):
    def add_tracks():
        video_track = VideoTransformTrack(camera)
        pc.addTrack(video_track)

        audio_track = AudioTransformTrack()
        pc.addTrack(audio_track)

    @pc.on("track")
    def on_track(track):
        print("Track %s received" % track.kind)

    add_tracks()

    await signaling.connect()

    while True:
        obj = await signaling.receive()

        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)

            if obj.type == "offer":
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                await signaling.send(pc.localDescription)
        elif obj is BYE:
            break
        else:
            print("Unknown message %s" % obj)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Video and audio stream from the Raspberry Pi")
    add_signaling_arguments(parser)
    args = parser.parse_args()

signaling = create_signaling(args)
pc = RTCPeerConnection()

camera = PiCamera()
camera.resolution = (640, 480)
camera.framerate = 30

loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(run(pc, signaling, camera))
except KeyboardInterrupt:
    pass
finally:
    loop.run_until_complete(pc.close())
    loop.run_until_complete(signaling.close())

