import numpy as np
import codec2
import ctypes
import structlog
import threading
import audio
import os
from modem_frametypes import FRAME_TYPE
import itertools

TESTMODE = False

class Demodulator():

    MODE_DICT = {}
    # Iterate over the FREEDV_MODE enum members
    for mode in codec2.FREEDV_MODE:
        MODE_DICT[mode.value] = {
            'decode': False,
            'bytes_per_frame': None,
            'bytes_out': None,
            'audio_buffer': None,
            'nin': None,
            'instance': None,
            'state_buffer': [],
            'name': mode.name.upper(),
            'decoding_thread': None
        }

    def __init__(self, config, audio_rx_q, modem_rx_q, data_q_rx, states, event_manager, fft_queue):
        self.log = structlog.get_logger("Demodulator")

        self.tuning_range_fmin = config['MODEM']['tuning_range_fmin']
        self.tuning_range_fmax = config['MODEM']['tuning_range_fmax']
        self.rx_audio_level = config['AUDIO']['rx_audio_level']

        self.AUDIO_FRAMES_PER_BUFFER_RX = 4800
        self.buffer_overflow_counter = [0, 0, 0, 0, 0, 0, 0, 0]
        self.is_codec2_traffic_counter = 0
        self.is_codec2_traffic_cooldown = 5

        self.audio_received_queue = audio_rx_q
        self.modem_received_queue = modem_rx_q
        self.data_queue_received = data_q_rx

        self.states = states
        self.event_manager = event_manager

        self.fft_queue = fft_queue

        # init codec2 resampler
        self.resampler = codec2.resampler()

        self.init_codec2()

        # enable decoding of signalling modes
        self.MODE_DICT[codec2.FREEDV_MODE.signalling.value]["decode"] = True

        tci_rx_callback_thread = threading.Thread(
            target=self.tci_rx_callback,
            name="TCI RX CALLBACK THREAD",
            daemon=True,
        )
        tci_rx_callback_thread.start()

    def init_codec2(self):
        # Open codec2 instances
        for mode in codec2.FREEDV_MODE:
            self.init_codec2_mode(mode.value)


    def init_codec2_mode(self, mode):
        """
        Init codec2 and return some important parameters
        """

        # create codec2 instance
        c2instance = ctypes.cast(
            codec2.api.freedv_open(mode), ctypes.c_void_p
        )

        # set tuning range
        codec2.api.freedv_set_tuning_range(
            c2instance,
            ctypes.c_float(float(self.tuning_range_fmin)),
            ctypes.c_float(float(self.tuning_range_fmax)),
        )

        # get bytes per frame
        bytes_per_frame = int(
            codec2.api.freedv_get_bits_per_modem_frame(c2instance) / 8
        )

        # create byte out buffer
        bytes_out = ctypes.create_string_buffer(bytes_per_frame)

        # set initial frames per burst
        codec2.api.freedv_set_frames_per_burst(c2instance, 1)

        # init audio buffer
        audio_buffer = codec2.audio_buffer(2 * self.AUDIO_FRAMES_PER_BUFFER_RX)

        # get initial nin
        nin = codec2.api.freedv_nin(c2instance)

        # Additional Datac0-specific information - these are not referenced anywhere else.
        # self.signalling_datac0_payload_per_frame = self.signalling_datac0_bytes_per_frame - 2
        # self.signalling_datac0_n_nom_modem_samples = codec2.api.freedv_get_n_nom_modem_samples(
        #     self.signalling_datac0_freedv
        # )
        # self.signalling_datac0_n_tx_modem_samples = codec2.api.freedv_get_n_tx_modem_samples(
        #     self.signalling_datac0_freedv
        # )
        # self.signalling_datac0_n_tx_preamble_modem_samples = (
        #     codec2.api.freedv_get_n_tx_preamble_modem_samples(self.signalling_datac0_freedv)
        # )
        # self.signalling_datac0_n_tx_postamble_modem_samples = (
        #     codec2.api.freedv_get_n_tx_postamble_modem_samples(self.signalling_datac0_freedv)
        # )

        self.MODE_DICT[mode]["instance"] = c2instance
        self.MODE_DICT[mode]["bytes_per_frame"] = bytes_per_frame
        self.MODE_DICT[mode]["bytes_out"] = bytes_out
        self.MODE_DICT[mode]["audio_buffer"] = audio_buffer
        self.MODE_DICT[mode]["nin"] = nin

    def start(self, stream):

        self.stream = stream

        for mode in self.MODE_DICT:
            # Start decoder threads
            self.MODE_DICT[mode]['decoding_thread'] = threading.Thread(
                target=self.demodulate_audio,args=[mode], name=self.MODE_DICT[mode]['name'], daemon=True
            )
            self.MODE_DICT[mode]['decoding_thread'].start()

    def sd_input_audio_callback(self, indata: np.ndarray, frames: int, time, status) -> None:
            audio_48k = np.frombuffer(indata, dtype=np.int16)
            audio_8k = self.resampler.resample48_to_8(audio_48k)

            audio_8k_level_adjusted = audio.set_audio_volume(audio_8k, self.rx_audio_level)
            audio.calculate_fft(audio_8k_level_adjusted, self.fft_queue, self.states)

            length_audio_8k_level_adjusted = len(audio_8k_level_adjusted)
            # Avoid buffer overflow by filling only if buffer for
            # selected datachannel mode is not full
            index = 0
            for mode in self.MODE_DICT:
                mode_data = self.MODE_DICT[mode]
                audiobuffer = mode_data['audio_buffer']
                decode = mode_data['decode']
                index += 1
                if audiobuffer:
                    if (audiobuffer.nbuffer + length_audio_8k_level_adjusted) > audiobuffer.size:
                        self.buffer_overflow_counter[index] += 1
                        self.event_manager.send_buffer_overflow(self.buffer_overflow_counter)
                    elif decode:
                        audiobuffer.push(audio_8k_level_adjusted)

    def worker_received(self) -> None:
        """Worker for FIFO queue for processing received frames"""
        while True:
            data = self.modem_received_queue.get()
            self.log.debug("[MDM] worker_received: received data!")
            # data[0] = bytes_out
            # data[1] = freedv session
            # data[2] = bytes_per_frame
            # data[3] = snr

            item = {
                'payload': data[0],
                'freedv': data[1],
                'bytes_per_frame': data[2],
                'snr': data[3],
                'frequency_offset': self.get_frequency_offset(data[1]),
            }

            self.data_queue_received.put(item)
            self.modem_received_queue.task_done()

    def get_frequency_offset(self, freedv: ctypes.c_void_p) -> float:
        """
        Ask codec2 for the calculated (audio) frequency offset of the received signal.

        :param freedv: codec2 instance to query
        :type freedv: ctypes.c_void_p
        :return: Offset of audio frequency in Hz
        :rtype: float
        """
        modemStats = codec2.MODEMSTATS()
        codec2.api.freedv_get_modem_extended_stats(freedv, ctypes.byref(modemStats))
        offset = round(modemStats.foff) * (-1)
        return offset

    def demodulate_audio(self, mode) -> int:
        """
        De-modulate supplied audio stream with supplied codec2 instance.
        Decoded audio is placed into `bytes_out`.
        """

        audiobuffer = self.MODE_DICT[mode]["audio_buffer"]
        nin = self.MODE_DICT[mode]["nin"]
        freedv = self.MODE_DICT[mode]["instance"]
        bytes_out = self.MODE_DICT[mode]["bytes_out"]
        bytes_per_frame= self.MODE_DICT[mode]["bytes_per_frame"]
        state_buffer = self.MODE_DICT[mode]["state_buffer"]
        mode_name = self.MODE_DICT[mode]["name"]
        try:
            while self.stream.active:
                threading.Event().wait(0.01)
                while audiobuffer.nbuffer >= nin:
                    # demodulate audio
                    nbytes = codec2.api.freedv_rawdatarx(
                        freedv, bytes_out, audiobuffer.buffer.ctypes
                    )
                    # get current modem states and write to list
                    # 1 trial
                    # 2 sync
                    # 3 trial sync
                    # 6 decoded
                    # 10 error decoding == NACK
                    rx_status = codec2.api.freedv_get_rx_status(freedv)

                    if rx_status not in [0]:
                        self.is_codec2_traffic_counter = self.is_codec2_traffic_cooldown
                        self.log.debug(
                            "[MDM] [demod_audio] modem state", mode=mode_name, rx_status=rx_status,
                            sync_flag=codec2.api.rx_sync_flags_to_text[rx_status]
                        )

                    # decrement codec traffic counter for making state smoother
                    if self.is_codec2_traffic_counter > 0:
                        self.is_codec2_traffic_counter -= 1
                        self.states.set_channel_busy_condition_codec2(True)
                    else:
                        self.states.set_channel_busy_condition_codec2(False)
                    if rx_status == 10:
                        state_buffer.append(rx_status)

                    audiobuffer.pop(nin)
                    nin = codec2.api.freedv_nin(freedv)
                    if nbytes == bytes_per_frame:
                        self.log.debug(
                            "[MDM] [demod_audio] Pushing received data to received_queue", nbytes=nbytes
                        )
                        snr = self.calculate_snr(freedv)
                        self.get_scatter(freedv)

                        self.modem_received_queue.put([bytes_out, freedv, bytes_per_frame, snr])
                        state_buffer = []
        except Exception as e:
            error_message = str(e)
            # we expect this error when shutdown
            if "PortAudio not initialized" in error_message:
                e = None
            self.log.debug(
                "[MDM] [demod_audio] demod loop ended", mode=mode_name, e=e
            )
    def tci_rx_callback(self) -> None:
        """
        Callback for TCI RX

        data_in48k must be filled with 48000Hz audio raw data

        """

        while True:

            audio_48k = self.audio_received_queue.get()
            audio_48k = np.frombuffer(audio_48k, dtype=np.int16)

            audio.calculate_fft(audio_48k, self.fft_queue, self.states)

            length_audio_48k = len(audio_48k)
            index = 0
            for mode in self.MODE_DICT:
                mode_data = self.MODE_DICT[mode]
                audiobuffer = mode_data['audio_buffer']
                decode = mode_data['decode']
                index += 1
                if audiobuffer:
                    if (audiobuffer.nbuffer + length_audio_48k) > audiobuffer.size:
                        self.buffer_overflow_counter[index] += 1
                        self.event_manager.send_buffer_overflow(self.buffer_overflow_counter)
                    elif decode:
                        audiobuffer.push(audio_48k)

    def set_frames_per_burst(self, frames_per_burst: int) -> None:
        """
        Configure codec2 to send the configured number of frames per burst.

        :param frames_per_burst: Number of frames per burst requested
        :type frames_per_burst: int
        """
        # Limit frames per burst to acceptable values
        frames_per_burst = min(frames_per_burst, 1)
        frames_per_burst = max(frames_per_burst, 5)

        frames_per_burst = 1

        codec2.api.freedv_set_frames_per_burst(self.dat0_datac1_freedv, frames_per_burst)
        codec2.api.freedv_set_frames_per_burst(self.dat0_datac3_freedv, frames_per_burst)
        codec2.api.freedv_set_frames_per_burst(self.dat0_datac4_freedv, frames_per_burst)

    def calculate_snr(self, freedv: ctypes.c_void_p) -> float:
        """
        Ask codec2 for data about the received signal and calculate
        the signal-to-noise ratio.

        :param freedv: codec2 instance to query
        :type freedv: ctypes.c_void_p
        :return: Signal-to-noise ratio of the decoded data
        :rtype: float
        """
        try:
            modem_stats_snr = ctypes.c_float()
            modem_stats_sync = ctypes.c_int()

            codec2.api.freedv_get_modem_stats(
                freedv, ctypes.byref(modem_stats_sync), ctypes.byref(modem_stats_snr)
            )
            modem_stats_snr = modem_stats_snr.value
            modem_stats_sync = modem_stats_sync.value

            snr = round(modem_stats_snr, 1)
            self.log.info("[MDM] calculate_snr: ", snr=snr)
            # snr = np.clip(
            #    snr, -127, 127
            # )  # limit to max value of -128/128 as a possible fix of #188
            return int(snr)
        except Exception as err:
            self.log.error(f"[MDM] calculate_snr: Exception: {err}")
            return 0

    def get_scatter(self, freedv: ctypes.c_void_p) -> None:
        """
        Ask codec2 for data about the received signal and calculate the scatter plot.

        :param freedv: codec2 instance to query
        :type freedv: ctypes.c_void_p
        """
       
        modemStats = codec2.MODEMSTATS()
        ctypes.cast(
            codec2.api.freedv_get_modem_extended_stats(freedv, ctypes.byref(modemStats)),
            ctypes.c_void_p,
        )

        scatterdata = []
        # original function before itertool
        # for i in range(codec2.MODEM_STATS_NC_MAX):
        #    for j in range(1, codec2.MODEM_STATS_NR_MAX, 2):
        #        # print(f"{modemStats.rx_symbols[i][j]} - {modemStats.rx_symbols[i][j]}")
        #        xsymbols = round(modemStats.rx_symbols[i][j - 1] // 1000)
        #        ysymbols = round(modemStats.rx_symbols[i][j] // 1000)
        #        if xsymbols != 0.0 and ysymbols != 0.0:
        #            scatterdata.append({"x": str(xsymbols), "y": str(ysymbols)})

        for i, j in itertools.product(range(codec2.MODEM_STATS_NC_MAX), range(1, codec2.MODEM_STATS_NR_MAX, 2)):
            # print(f"{modemStats.rx_symbols[i][j]} - {modemStats.rx_symbols[i][j]}")
            xsymbols = round(modemStats.rx_symbols[i][j - 1] // 1000)
            ysymbols = round(modemStats.rx_symbols[i][j] // 1000)
            if xsymbols != 0.0 and ysymbols != 0.0:
                scatterdata.append({"x": str(xsymbols), "y": str(ysymbols)})

        # Send all the data if we have too-few samples, otherwise send a sampling
        if 150 > len(scatterdata) > 0:
            self.event_manager.send_scatter_change(scatterdata)

        else:
            # only take every tenth data point
            self.event_manager.send_scatter_change(scatterdata[::10])

    def reset_data_sync(self) -> None:
        """
        reset sync state for modes

        :param frames_per_burst: Number of frames per burst requested
        :type frames_per_burst: int
        """
        for mode in self.MODE_DICT:
            codec2.api.freedv_set_sync(self.MODE_DICT[mode]["instance"], 0)

    def set_decode_mode(self, mode):

        for m in self.MODE_DICT: self.MODE_DICT[m]["decode"] = False

        # signalling is always true
        self.MODE_DICT[codec2.FREEDV_MODE.signalling.value]["decode"] = True

        # Enable mode based on speed_level
        self.MODE_DICT[mode.value]["decode"] = True
        self.log.info(f"[MDM] [demod_audio] set data mode: {mode.name}")

        return
