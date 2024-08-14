from beatrice_python_sample.audio_device import AudioDevice

from beatrice_python.simple_beatrice import SimpleBeatrice
from beatrice_python_sample.cui.front import CuiFront
import fire
import sounddevice as sd
import multiprocessing as mp
from beatrice_python_sample.gpu_device_manager import reload_gpu_info


def file_convert_demo(in_filename: str, out_filename: str, target_speaker_id: int = 1, pitch_shift_semitones: float = 0,
                      formant_shift_semitones: float = 0):
    """
    Convert audio file using Beatrice.
    Args:
        in_filename (str): Input audio file path (16Khz, wav format only).
        out_filename (str): Output audio file path.
        target_speaker_id (int, optional): Target speaker ID. Defaults to 1.
        pitch_shift_semitones (float, optional): Pitch shift in semitones. Defaults to 1.0.
        formant_shift_semitones (float, optional): Formant shift in semitones. Defaults to 0.0. [-2.0, 2.0] で 0.5 刻み

    ex)
    poetry run beatrice_python_sample file_convert_demo jvs001_16k.wav out.wav
    """
    print("start convert...")
    beatrice = SimpleBeatrice()
    print("start convert...initialized")
    beatrice.convert_file(in_filename, out_filename, target_speaker_id=target_speaker_id,
                          pitch_shift_semitones=pitch_shift_semitones)
    print("start convert...initialized...converted")


def _list_device():
    try:
        audio_device_list = sd.query_devices()
    except Exception as e:
        print("list device ex:query_devices")
        raise e

    input_audio_device_list = [d for d in audio_device_list if d['max_input_channels'] > 0]
    output_audio_device_list = [d for d in audio_device_list if d['max_output_channels'] > 0]

    hostapis = sd.query_hostapis()

    audio_input_devices = []
    audio_output_devices = []

    for d in input_audio_device_list:
        input_audio_device = AudioDevice(
            kind='audioinput',
            index=d['index'],
            name=d['name'],
            host_api=hostapis[d['hostapi']]['name'],
            max_input_channels=d['max_input_channels'],
            max_output_channels=d['max_output_channels'],
            default_samplerate=d['default_samplerate']
        )
        audio_input_devices.append(input_audio_device)

    for d in output_audio_device_list:
        output_audio_device = AudioDevice(
            kind='audiooutput',
            index=d['index'],
            name=d['name'],
            host_api=hostapis[d['hostapi']]['name'],
            max_input_channels=d['max_input_channels'],
            max_output_channels=d['max_output_channels'],
            default_samplerate=d['default_samplerate']
        )
        audio_output_devices.append(output_audio_device)

    return audio_input_devices, audio_output_devices


def realtime_convert_demo(exclusive_mode: bool = True):
    reload_gpu_info()
    audio_input_devices, audio_output_devices = _list_device()
    CuiFront(audio_input_devices, audio_output_devices).run()


def main():
    mp.freeze_support()
    fire.Fire({
        'file_convert_demo': file_convert_demo,
        'realtime_convert_demo': realtime_convert_demo
    })


if __name__ == '__main__':
    main()