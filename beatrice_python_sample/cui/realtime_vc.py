import time
from beatrice_python_sample.cui.frontend import Frontend
import numpy as np
from beatrice_python_sample.audio_device import AudioDevice
from beatrice_python_sample.cui.config import Config
import sounddevice as sd
from beatrice_python.simple_beatrice import SimpleBeatrice
from queue import Queue
import samplerate as sr
import threading
from beatrice import IN_HOP_LENGTH, IN_SAMPLE_RATE, OUT_SAMPLE_RATE

class ReailtimeVC:
    def __init__(self, audio_input_devices: list[AudioDevice],
                 audio_output_devices: list[AudioDevice],
                 exclusive_mode=True, block_num=1):
        self.audio_input_devices = audio_input_devices
        self.audio_output_devices = audio_output_devices
        self.exclusive_mode = exclusive_mode
        self.block_num = block_num
        self.exception = None

    def start(self, app: Frontend):
        try:
            self._start()
        except Exception as e:
            self.exception = e
            try:
                app.notify_exception_end(str(e))
            except Exception as e2:
                with open('exception.txt', 'w') as f:
                    f.write(f"{e2}")

    def _start(self):
        current_input_devices = [audio_input_device for audio_input_device in self.audio_input_devices
                                 if audio_input_device.index == Config.get_instance().input_device]
        if len(current_input_devices) == 0:
            raise RuntimeError(f"Invalid input device {Config.get_instance().input_device}")
        current_input_device = current_input_devices[0]

        current_output_devices = [audio_output_device for audio_output_device in self.audio_output_devices
                                  if audio_output_device.index == Config.get_instance().output_device]
        if len(current_output_devices) == 0:
            raise RuntimeError(f"Invalid output device {Config.get_instance().input_device}")
        current_output_device = current_output_devices[0]

        input_extra_settings = None
        if 'WASAPI' in current_input_device.host_api and self.exclusive_mode is True:
            print('WASAPI exclusive mode(i): on')
            input_extra_settings = sd.WasapiSettings(exclusive=True)

        output_extra_settings = None
        if 'WASAPI' in current_output_device.host_api and self.exclusive_mode is True:
            print('WASAPI exclusive mode(o): on')
            output_extra_settings = sd.WasapiSettings(exclusive=True)

        class BeatriceCallback:
            input_sample_rate = -1
            output_sample_rate = -1
            input_channels = -1
            output_channels = -1

            def __init__(self):
                self.beatrice = SimpleBeatrice()
                self.out_queue = Queue()
                self.in_queue = Queue()
                self.input_resampler = None
                self.output_resampler = None
                self.skip_count = 0
                self.truncate_count = 0
                self.stop_flag = False

            def set_stream_info(self, input_sample_rate, output_sample_rate, input_channels, output_channels):
                self.input_sample_rate = input_sample_rate
                self.output_sample_rate = output_sample_rate
                self.input_channels = input_channels
                self.output_channels = output_channels

                input_resample_ratio = IN_SAMPLE_RATE / input_sample_rate
                self.input_resampler = sr.CallbackResampler(self.get_input_producer(), ratio=input_resample_ratio,
                                                            converter_type='sinc_best')
                self.thread1 = threading.Thread(target=self.input_resampler_monitor)
                self.thread1.start()

                output_resample_ratio = output_sample_rate / OUT_SAMPLE_RATE
                self.output_resampler = sr.CallbackResampler(self.get_output_producer(), ratio=output_resample_ratio,
                                                             converter_type='sinc_best')

            def audio_input_callback(self, indata: np.ndarray, frames, times, status):
                try:
                    if status:
                        print(status)
                    if self.input_sample_rate == -1:
                        print('waiting for stream info')
                        return
                    if self.input_resampler is None:
                        print('waiting for resampler')
                        return
                    indata = indata[:, 0]
                    self.in_queue.put(indata.copy())
                except Exception as e:
                    print('audio input callback ex:', e)

            def get_input_producer(self):
                def producer():
                    while True:
                        data = self.in_queue.get()
                        yield data

                return lambda: next(producer())

            def get_output_producer(self):
                def producer():
                    while True:
                        data = self.out_queue.get()
                        yield data

                return lambda: next(producer())

            def input_resamlper_monitor(self):
                while not self.stop_flag:
                    resampled_input = self.input_resampler.read(IN_HOP_LENGTH)
                    formant_shift_semitones = Config.get_instance().formant_shift
                    if formant_shift_semitones not in (2, 1.5, 1, 0.5, 0, -0.5, -1, -1.5, -2):
                        formant_shift_semitones = 0
                    converted = self.beatrice.convert_segment(
                        resampled_input,
                        Config.get_instance().dst_sid,
                        Config.get_instance().pitch_shift,
                        formant_shift_semitones
                    )
                    self.out_queue.put(converted)

            def input_resampler_monitor(self):
                while not self.stop_flag:
                    resampled_input = self.input_resampler.read(IN_HOP_LENGTH)
                    formant_shift_semitones = Config.get_instance().formant_shift
                    if formant_shift_semitones not in (2, 1.5, 1, 0.5, 0, -0.5, -1, -1.5, -2):
                        formant_shift_semitones = 0
                    converted = self.beatrice.convert_segment(
                        resampled_input, Config.get_instance().dst_sid, Config.get_instance().pitch_shift,
                        formant_shift_semitones
                    )
                    self.out_queue.put(converted)

            # def get_output_producer(self):
            #     def producer():
            #         while True:
            #             data = self.out_queue.get()
            #             yield data
            #     return lambda p: next(p), producer()

            def audio_output_callback(self, outdata: np.ndarray, frames, times, status):
                try:
                    if status:
                        print(status)
                    if self.output_sample_rate == -1:
                        print('waiting for stream info')
                        return
                    if self.output_resampler is None:
                        print('waiting for resampler')
                        return
                    if self.stop_flag is True:
                        return
                    out_wav = self.output_resampler.read(outdata.shape[0])
                    out_wav = out_wav.reshape(-1, 1)
                    out_wav = np.repeat(out_wav, outdata.shape[1]).reshape(-1, outdata.shape[1])
                    outdata[:] = out_wav[:]
                except Exception as e:
                    print('audio output callback ex:', e)

            def stop(self):
                print('Stopping callback thread')
                self.stop_flag = True
                self.in_queue.put(np.zeros(IN_HOP_LENGTH * 10))
                self.thread1.join()

        callback = BeatriceCallback()

        with sd.InputStream(device=current_input_device.index, callback=callback.audio_input_callback) as stream:
            input_sample_rate = stream.samplerate

        input_block_size = int(round(input_sample_rate / IN_SAMPLE_RATE * IN_HOP_LENGTH))
        input_block_size *= self.block_num
        print(f"Input Block Size:{input_block_size}")

        with sd.OutputStream(device=current_output_device.index, callback=callback.audio_output_callback) as stream:
            output_sample_rate = stream.samplerate

        output_block_size = int(round(output_sample_rate * 0.01))
        output_block_size *= self.block_num
        print(f"Output Block Size:{output_block_size}")

        with sd.InputStream(device=current_input_device.index, callback=callback.audio_input_callback,
                            blocksize=input_block_size, extra_settings=input_extra_settings) as input_stream:
            with sd.OutputStream(device=current_output_device.index, callback=callback.audio_output_callback,
                                 blocksize=output_block_size, extra_settings=output_extra_settings) as output_stream:
                callback.set_stream_info(input_stream.samplerate, output_stream.samplerate,
                                         input_stream.channels, output_stream.channels)
                while True:
                    try:
                        time.sleep(1)
                        if Config.get_instance().started is False:
                            break
                    except Exception as e:
                        print('cmd ext:', e)
                    except KeyboardInterrupt:
                        print('KeyboardInterrupt')
                        break

            output_stream.close()
            input_stream.close()
            callback.stop()