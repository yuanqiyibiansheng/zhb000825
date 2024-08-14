from time import perf_counter
import numpy as np
from scipy.io import wavfile
from pathlib import Path
from beatrice import IN_HOP_LENGTH, IN_SAMPLE_RATE, OUT_SAMPLE_RATE, PITCH_BINS, PITCH_BINS_PER_OCTAVE, PhoneExtractor, \
    PitchEstimator, WaveformGenerator, read_speaker_embeddings

DEFAULT_PHONE_EXTRACTOR_FILE = 'beatrice-api/build/sample_inputs/phone_extractor.bin'
DEFAULT_PITCH_ESTIMATOR_FILE = 'beatrice-api/build/sample_inputs/pitch_estimator.bin'
DEFAULT_FORMANT_SHIFT_EMBEDDINGS_FILE = 'beatrice-api/build/sample_inputs/formant_shift_embeddings.bin'
DEFAULT_SPEAKER_EMBEDDINGS_FILE = 'beatrice-api/build/sample_inputs/speaker_embeddings.bin'
DEFAULT_WAVEFORM_GENERATOR_FILE = 'beatrice-api/build/sample_inputs/waveform_generator.bin'


class SimpleBeatrice:
    '''
    SimpleBeatrice is a simple wrapper class for Beatrice API.
    '''

    def __init__(self, phone_extractor_parameter_file=None, pitch_estimator_parameter_file=None,
                 formant_shift_embeddings_file=None, speaker_embeddings_file=None,
                 waveform_generator_parameter_file=None):
        '''
        Initialize SimpleBeatrice instance.
        Args:
            phone_extractor_parameter_file (str, optional): Path to the phone extractor parameter file. Defaults to None.
            pitch_estimator_parameter_file (str, optional): Path to the pitch estimator parameter file. Defaults to None.
            formant_shift_embeddings_file (str, optional): Path to the formant shift embeddings file. Defaults to None.
            speaker_embeddings_file (str, optional): Path to the speaker embeddings file. Defaults to None.
            waveform_generator_parameter_file (str, optional): Path to the waveform generator parameter file. Defaults to None.
        '''
        if phone_extractor_parameter_file is None:
            self.phone_extractor_parameter_file = Path(__file__).parent.parent / DEFAULT_PHONE_EXTRACTOR_FILE
        else:
            self.phone_extractor_parameter_file = Path(phone_extractor_parameter_file)
        if pitch_estimator_parameter_file is None:
            self.pitch_estimator_parameter_file = Path(__file__).parent.parent / DEFAULT_PITCH_ESTIMATOR_FILE
        else:
            self.pitch_estimator_parameter_file = Path(pitch_estimator_parameter_file)
        if formant_shift_embeddings_file is None:
            self.formant_shift_embeddings_file = Path(__file__).parent.parent / DEFAULT_FORMANT_SHIFT_EMBEDDINGS_FILE
        else:
            self.formant_shift_embeddings_file = Path(formant_shift_embeddings_file)
        if speaker_embeddings_file is None:
            self.speaker_embeddings_file = Path(__file__).parent.parent / DEFAULT_SPEAKER_EMBEDDINGS_FILE
        else:
            self.speaker_embeddings_file = Path(speaker_embeddings_file)
        if waveform_generator_parameter_file is None:
            self.waveform_generator_parameter_file = Path(__file__).parent.parent / DEFAULT_WAVEFORM_GENERATOR_FILE
        else:
            self.waveform_generator_parameter_file = Path(waveform_generator_parameter_file)
        self.phone_extractor = PhoneExtractor()
        self.phone_extractor.read_parameters(self.phone_extractor_parameter_file)
        self.pitch_estimator = PitchEstimator()
        self.pitch_estimator.read_parameters(self.pitch_estimator_parameter_file)
        self.formant_shift_embeddings = read_speaker_embeddings(self.formant_shift_embeddings_file)
        self.speaker_embeddings = read_speaker_embeddings(self.speaker_embeddings_file)
        self.waveform_generator = WaveformGenerator()
        self.waveform_generator.read_parameters(self.waveform_generator_parameter_file)
        self.block_size = 1
        self.phone_ctx = self.phone_extractor.new_context(self.block_size)
        self.pitch_ctx = self.pitch_estimator.new_context(self.block_size)
        self.waveform_ctx = self.waveform_generator.new_context(self.block_size)

    def convert_segment(self, source_wav_segment, target_speaker_id=1, pitch_shift_semitones=0.0, formant_shift_semitones=0.0):
        '''
        Convert a segment of audio waveform.
        Args:
            source_wav_segment (np.ndarray): Source audio waveform segment.
            target_speaker_id (int, optional): Target speaker ID. Defaults to 1.
            pitch_shift_semitones (float, optional): Pitch shift in semitones. Defaults to 0.0.
            formant_shift_semitones (float, optional): Formant shift in semitones. Defaults to 0.0. [-2.0, 2.0] で 0.5 刻み
        '''
        block_size_in_input_sample_rate = self.block_size * IN_HOP_LENGTH
        if len(source_wav_segment) < block_size_in_input_sample_rate:
            source_wav_segment = np.pad(source_wav_segment,
                                        (0, block_size_in_input_sample_rate - len(source_wav_segment)))
        phone = self.phone_extractor(source_wav_segment, self.phone_ctx)
        quantized_pitch, pitch_features = self.pitch_estimator(source_wav_segment, self.pitch_ctx)
        quantized_pitch = (quantized_pitch + int(round(pitch_shift_semitones * PITCH_BINS_PER_OCTAVE / 12))).clip(1,
                                                                                                                  PITCH_BINS - 1)
        speaker_embedding = self.speaker_embeddings[[target_speaker_id] * self.block_size]
        speaker_embedding += self.formant_shift_embeddings[4 + int(round(formant_shift_semitones * 2))]
        converted_wav_segment = self.waveform_generator(phone, quantized_pitch, pitch_features, speaker_embedding,
                                                        self.waveform_ctx)
        return converted_wav_segment

    def convert_file(self, in_filename, out_filename, target_speaker_id=1, pitch_shift_semitones=0.0, formant_shift_semitones=0.0):
        block_size_in_input_sample_rate = self.block_size * IN_HOP_LENGTH

        sr, source_wav = wavfile.read(in_filename)

        assert sr == IN_SAMPLE_RATE, "Sample rate mismatch"
        assert source_wav.ndim == 1, "Audio data is not mono"
        assert source_wav.dtype == np.int16, "Audio data is not 16-bit PCM"

        source_wav = source_wav / 32768.0
        source_wav = source_wav.astype(np.float32)

        converted_wav_segments = []
        t0 = perf_counter()

        for left in range(0, len(source_wav), block_size_in_input_sample_rate):
            source_wav_segment = source_wav[left:left + block_size_in_input_sample_rate]
            converted_wav_segment = self.convert_segment(source_wav_segment, target_speaker_id, pitch_shift_semitones,
                                                         formant_shift_semitones)
            converted_wav_segments.append(converted_wav_segment)

        elapsed_time = perf_counter() - t0
        rtf = elapsed_time / (len(source_wav) / sr)

        print(f"Elapsed time: {elapsed_time:.3f}s")
        print(f"RTF: {rtf:.3f}")

        converted_wav = np.concatenate(converted_wav_segments)

        wavfile.write(out_filename, OUT_SAMPLE_RATE, np.round(converted_wav * 32767).astype(np.int16))
