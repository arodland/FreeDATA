#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from enum import Enum


class FRAME_TYPE(Enum):
    """Lookup for frame types"""
    ARQ_CONNECTION_OPEN = 1
    ARQ_CONNECTION_HB = 2
    ARQ_CONNECTION_CLOSE = 3
    ARQ_STOP = 10
    ARQ_STOP_ACK = 11
    ARQ_SESSION_OPEN = 12
    ARQ_SESSION_OPEN_ACK = 13
    ARQ_SESSION_INFO = 14
    ARQ_SESSION_INFO_ACK = 15
    ARQ_BURST_FRAME = 20
    ARQ_BURST_ACK = 21
    MESH_BROADCAST = 100
    MESH_SIGNALLING_PING = 101
    MESH_SIGNALLING_PING_ACK = 102
    CQ = 200
    QRV = 201
    PING = 210
    PING_ACK = 211
    IS_WRITING = 215
    BEACON = 250
    FEC = 251
    FEC_WAKEUP = 252
    IDENT = 254
    TEST_FRAME = 255
