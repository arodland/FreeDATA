import threading
import arq_session
import helpers
from modem_frametypes import FRAME_TYPE
from codec2 import FREEDV_MODE
from enum import Enum

class IRS_State(Enum):
    NEW = 0
    OPEN_ACK_SENT = 1
    INFO_ACK_SENT = 2
    BURST_REPLY_SENT = 3
    ENDED = 4
    FAILED = 5

class ARQSessionIRS(arq_session.ARQSession):

    RETRIES_CONNECT = 3
    RETRIES_TRANSFER = 3 # we need to increase this

    TIMEOUT_CONNECT = 3
    TIMEOUT_DATA = 12

    STATE_TRANSITION = {
        IRS_State.NEW: { 
            FRAME_TYPE.ARQ_SESSION_OPEN.value : 'send_open_ack',
        },
        IRS_State.OPEN_ACK_SENT: { 
            FRAME_TYPE.ARQ_SESSION_OPEN.value: 'send_open_ack',
            FRAME_TYPE.ARQ_SESSION_INFO.value: 'send_info_ack',
        },
        IRS_State.INFO_ACK_SENT: {
            FRAME_TYPE.ARQ_SESSION_INFO.value: 'send_info_ack',
            FRAME_TYPE.ARQ_BURST_FRAME.value: 'receive_data',
        },
        IRS_State.BURST_REPLY_SENT: {
            FRAME_TYPE.ARQ_BURST_FRAME.value: 'receive_data',
        },
    }

    def __init__(self, config: dict, modem, dxcall: str, session_id: int):
        super().__init__(config, modem, dxcall)

        self.id = session_id
        self.dxcall = dxcall
        self.version = 1

        self.state = IRS_State.NEW

        self.total_length = 0
        self.total_crc = ''
        self.received_data = None
        self.received_bytes = 0
        self.received_crc = None

        self.transmitted_acks = 0

    def set_decode_mode(self):
        self.modem.demodulator.set_decode_mode(self.get_mode_by_speed_level(self.speed_level))

    def all_data_received(self):
        return self.total_length == self.received_bytes

    def final_crc_matches(self) -> bool:
        match = self.total_crc == helpers.get_crc_32(bytes(self.received_data)).hex()
        return match

    def transmit_and_wait(self, frame, timeout, mode):
        self.transmit_frame(frame, mode)
        self.log(f"Waiting {timeout} seconds...")
        if not self.event_frame_received.wait(timeout):
            # use case: data burst got lost, we want to send a NACK with updated speed level
            if self.state in [IRS_State.BURST_REPLY_SENT, IRS_State.INFO_ACK_SENT]:
                self.transmitted_acks = 0
                self.calibrate_speed_settings()
                self.send_burst_nack()
                return

            self.log("Timeout waiting for ISS. Session failed.")
            self.set_state(IRS_State.FAILED)
            self.event_manager.send_arq_finished(False, self.id, self.dxcall, self.total_length, False)

    def launch_transmit_and_wait(self, frame, timeout, mode):
        thread_wait = threading.Thread(target = self.transmit_and_wait, 
                                       args = [frame, timeout, mode])
        thread_wait.start()
    
    def send_open_ack(self, open_frame):
        ack_frame = self.frame_factory.build_arq_session_open_ack(
            self.id,
            self.dxcall, 
            self.version,
            self.snr[0])
        self.launch_transmit_and_wait(ack_frame, self.TIMEOUT_CONNECT, mode=FREEDV_MODE.signalling)
        self.set_state(IRS_State.OPEN_ACK_SENT)

    def send_info_ack(self, info_frame):
        # Get session info from ISS
        self.received_data = bytearray(info_frame['total_length'])
        self.total_length = info_frame['total_length']
        self.total_crc = info_frame['total_crc']
        self.dx_snr.append(info_frame['snr'])

        self.log(f"New transfer of {self.total_length} bytes")
        self.event_manager.send_arq_session_new(False, self.id, self.dxcall, self.total_length)

        self.calibrate_speed_settings()
        self.set_decode_mode()
        info_ack = self.frame_factory.build_arq_session_info_ack(
            self.id, self.total_crc, self.snr[0],
            self.speed_level, self.frames_per_burst)
        self.launch_transmit_and_wait(info_ack, self.TIMEOUT_CONNECT, mode=FREEDV_MODE.signalling)
        self.set_state(IRS_State.INFO_ACK_SENT)

    def send_burst_nack(self):
        self.calibrate_speed_settings()
        self.set_decode_mode()
        nack = self.frame_factory.build_arq_burst_ack(self.id, self.received_bytes, self.speed_level, self.frames_per_burst, self.snr[0])
        self.transmit_frame(nack, mode=FREEDV_MODE.signalling)

    def process_incoming_data(self, frame):
        if frame['offset'] != self.received_bytes:
            self.log(f"Discarding data offset {frame['offset']}")
            return False

        remaining_data_length = self.total_length - self.received_bytes

        # Is this the last data part?
        if remaining_data_length <= len(frame['data']):
            # we only want the remaining length, not the entire frame data
            data_part = frame['data'][:remaining_data_length]
        else:
            # we want the entire frame data
            data_part = frame['data']

        self.received_data[frame['offset']:] = data_part
        self.received_bytes += len(data_part)
        self.log(f"Received {self.received_bytes}/{self.total_length} bytes")
        self.event_manager.send_arq_session_progress(
            False, self.id, self.dxcall, self.received_bytes, self.total_length)

        return True

    def receive_data(self, burst_frame):
        self.process_incoming_data(burst_frame)
        self.calibrate_speed_settings()
        ack = self.frame_factory.build_arq_burst_ack(
            self.id, self.received_bytes, 
            self.speed_level, self.frames_per_burst, self.snr[0])

        if not self.all_data_received():
            # increase ack counter
            self.transmitted_acks += 1
            self.transmit_frame(ack, mode=FREEDV_MODE.signalling)
            self.set_state(IRS_State.BURST_REPLY_SENT)
            return

        if self.final_crc_matches():
            self.log("All data received successfully!")
            self.transmit_frame(ack, mode=FREEDV_MODE.signalling)
            self.set_state(IRS_State.ENDED)
            self.event_manager.send_arq_session_finished(
                False, self.id, self.dxcall, self.total_length, True)

        else:
            self.log("CRC fail at the end of transmission!")
            self.set_state(IRS_State.FAILED)
            self.event_manager.send_arq_session_finished(
                False, self.id, self.dxcall, self.total_length, False)


    def calibrate_speed_settings(self):
        self.speed_level = 0 # for now stay at lowest speed level
        return
        # if we have two ACKS, then consider increasing speed level
        if self.transmitted_acks >= 2:
            self.transmitted_acks = 0
            new_speed_level = min(self.speed_level + 1, len(self.SPEED_LEVEL_DICT) - 1)

            # check first if the next mode supports the actual snr
            if self.snr[0] >= self.SPEED_LEVEL_DICT[new_speed_level]["min_snr"]:
                self.speed_level = new_speed_level

