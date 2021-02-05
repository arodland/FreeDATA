#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Dec 27 20:43:40 2020

@author: DJ2LS
"""

import logging
import threading
import time
from random import randrange

import static
import modem
import helpers
import main

modem = modem.RF()

static.ARQ_PAYLOAD_PER_FRAME = static.FREEDV_DATA_PAYLOAD_PER_FRAME - 3 #6?!
static.ARQ_ACK_PAYLOAD_PER_FRAME = 14 - 2#

def arq_ack_timeout():
    static.ARQ_ACK_TIMEOUT = 1

    
def data_received(data_in):


#            arqframe = frame_type + \                                    # 1 [:1]  # frame type and current number of arq frame of (current) burst 
#                       bytes([static.ARQ_TX_N_FRAMES_PER_BURST]) + \     # 1 [1:2] # total number of arq frames per (current) burst 
#                       static.ARQ_N_CURRENT_ARQ_FRAME + \                # 2 [2:4] # current arq frame number 
#                       static.ARQ_N_TOTAL_ARQ_FRAMES + \                 # 2 [4:6] # total number arq frames 
#                       static.ARQ_BURST_PAYLOAD_CRC + \                  # 2 [6:8] # arq crc 
#                       payload_data                                      # N [8:N] # payload data 





    
        static.ARQ_N_FRAME = int.from_bytes(bytes(data_in[:1]), "big")  - 10 #get number of burst frame
        static.ARQ_N_RX_FRAMES_PER_BURSTS = int.from_bytes(bytes(data_in[1:2]), "big") #get number of bursts from received frame
        static.ARQ_RX_N_CURRENT_ARQ_FRAME = int.from_bytes(bytes(data_in[2:4]), "big") #get current number of total frames
        static.ARQ_N_ARQ_FRAMES_PER_DATA_FRAME = int.from_bytes(bytes(data_in[4:6]), "big") # get get total number of frames
        static.ARQ_BURST_PAYLOAD_CRC = data_in[6:8]
        
        
        print("----------------------------------------------------------------")
        logging.info("ARQ_N_FRAME: " + str(static.ARQ_N_FRAME))
        logging.info("ARQ_N_RX_FRAMES_PER_BURSTS: " + str(static.ARQ_N_RX_FRAMES_PER_BURSTS))
        logging.info("ARQ_RX_N_CURRENT_ARQ_FRAME: " + str(static.ARQ_RX_N_CURRENT_ARQ_FRAME))
        logging.info("ARQ_N_ARQ_FRAMES_PER_DATA_FRAME: " + str(static.ARQ_N_ARQ_FRAMES_PER_DATA_FRAME))
        logging.info("static.ARQ_BURST_PAYLOAD_CRC: " + str(static.ARQ_BURST_PAYLOAD_CRC))
        print("----------------------------------------------------------------")

        
        arq_percent_burst = int((static.ARQ_N_FRAME / static.ARQ_N_RX_FRAMES_PER_BURSTS)*100)
        arq_percent_frame = int(((static.ARQ_RX_N_CURRENT_ARQ_FRAME)/static.ARQ_N_ARQ_FRAMES_PER_DATA_FRAME)*100)      
        
        logging.info("ARQ | RX | ARQ FRAME [" + str(static.ARQ_N_FRAME) + "/" + str(static.ARQ_N_RX_FRAMES_PER_BURSTS) + "] [" + str(arq_percent_burst).zfill(3) + "%] --- TOTAL [" + str(static.ARQ_RX_N_CURRENT_ARQ_FRAME) + "/" + str(static.ARQ_N_ARQ_FRAMES_PER_DATA_FRAME) + "] [" + str(arq_percent_frame).zfill(3) + "%]" )
    
    
    
        #allocate ARQ_RX_FRAME_BUFFER as a list with "None" if not already done. This should be done only once per burst!
        # here we will save the N frame of a data frame to N list position so we can explicit search for it
        if static.ARQ_N_ARQ_FRAMES_PER_DATA_FRAME != len(static.ARQ_RX_FRAME_BUFFER) and static.ARQ_RX_N_CURRENT_ARQ_FRAME == 1:
            for i in range(0,static.ARQ_N_ARQ_FRAMES_PER_DATA_FRAME+1):
                static.ARQ_RX_FRAME_BUFFER.insert(i,None)
                
 
        #allocate ARQ_RX_BURST_BUFFER as a list with "None" if not already done. This should be done only once per burst!
        # here we will save the N frame of a burst to N list position so we can explicit search for it
        if static.ARQ_N_RX_FRAMES_PER_BURSTS != len(static.ARQ_RX_BURST_BUFFER) and static.ARQ_N_FRAME == 1:
            for i in range(0,static.ARQ_N_RX_FRAMES_PER_BURSTS+1):
                static.ARQ_RX_BURST_BUFFER.insert(i,None)
            
        
        

        # now we add the incoming data to the specified position in our lists
        static.ARQ_RX_BURST_BUFFER[static.ARQ_N_FRAME] = bytes(data_in) 
        static.ARQ_RX_FRAME_BUFFER[static.ARQ_RX_N_CURRENT_ARQ_FRAME] = bytes(data_in)  
                    

# -------------------------- ARQ BURST CHECKER
        
        # run only if we recieved all ARQ FRAMES per ARQ BURST
        burst_total_payload = bytearray()
        if static.ARQ_N_FRAME == static.ARQ_N_RX_FRAMES_PER_BURSTS: #if received bursts are equal to burst number in frame
            
            #here we get the total payload for the frame to calculate the crc        
            for n_raw_frame in range(1,len(static.ARQ_RX_BURST_BUFFER)):
                # we need to check if we have a None or received data in list
                if static.ARQ_RX_BURST_BUFFER[n_raw_frame] != None:
                    burst_frame = static.ARQ_RX_BURST_BUFFER[n_raw_frame] #get burst frame
                    burst_payload = burst_frame[8:] #remove frame type and burst CRC     #4
                    burst_total_payload = burst_total_payload + burst_payload #stick bursts together

            # ------------------ calculate CRC of BURST          
            burst_payload_crc = helpers.get_crc_16(burst_total_payload)
            # IF BURST CRC IS CORRECT, APPEND BURST TO BUFFER AND SEND ACK FRAME
            if burst_payload_crc == data_in[6:8]:
                          
                #BUILDING ACK FRAME FOR BURST -----------------------------------------------              
                ack_payload = bytes(burst_payload_crc)
                ack_frame = b'<'+ bytes(burst_payload_crc) # < = 60   
                ack_buffer = bytearray(static.ARQ_ACK_PAYLOAD_PER_FRAME) 
                ack_buffer[:len(ack_frame)] = ack_frame # set buffersize to length of data which will be send                 
            
                #TRANSMIT ACK FRAME FOR BURST-----------------------------------------------
                logging.info("ARQ | TX | ARQ BURST ACK [" + str(data_in[6:8].hex()) +"]") #1:3
                modem.transmit_arq_ack(ack_buffer)

                # ----------------------------------------------------------------   
                static.ARQ_RX_BURST_BUFFER = [] # CLEAR RX BURST BUFFER AFTER SENDING DATA
                
            else: #IF burst payload crc and input crc are NOT equal
                logging.info("ARQ BURST CRC NOT EQUAL! [" + str(data_in[6:8]) + "]")
                static.ARQ_RX_BURST_BUFFER = []  #erase ARQ RX Burst buffer
        
        #if nframes are unequal to expected frames per burst
        else:
            print("unequal")
            pass
        
# ---------------------------- FRAME MACHINE
        
        # --------------- CHECK IF WE ARE MISSING FRAMES -------------------------------------------
        for frame in range(1,len(static.ARQ_RX_FRAME_BUFFER)):
            if static.ARQ_RX_FRAME_BUFFER[frame] == None:
                print("Missing frames:" + str(frame))
        
        # ---------------  IF LIST NOT CONTAINS "None" stick everything together 
        complete_data_frame = bytearray()   
        if static.ARQ_RX_FRAME_BUFFER.count(None) == 1: ## 1 because position 0 of list will alaways be None in our case
            print("ALL DATA RECEIVED!")
            
            for frame in range(1,len(static.ARQ_RX_FRAME_BUFFER)):
                raw_arq_frame = static.ARQ_RX_FRAME_BUFFER[frame]
                arq_frame_payload = raw_arq_frame[8:]
                
                # -------- DETECT IF WE RECEIVED A FRAME HEADER THEN SAVE DATA TO GLOBALS
                if arq_frame_payload[2:4].startswith(static.FRAME_BOF):
                    static.FRAME_CRC = arq_frame_payload[:2]
                    static.ARQ_FRAME_BOF_RECEIVED = True
                    
                    arq_frame_payload = arq_frame_payload.split(static.FRAME_BOF)
                    arq_frame_payload = arq_frame_payload[1]
                    
                # -------- DETECT IF WE RECEIVED A FRAME FOOTER THEN SAVE DATA TO GLOBALS    
                if arq_frame_payload.rstrip(b'\x00').endswith(static.FRAME_EOF):
                    static.ARQ_FRAME_EOF_RECEIVED = True
                    
                    arq_frame_payload = arq_frame_payload.split(static.FRAME_EOF)
                    arq_frame_payload = arq_frame_payload[0]
                    
                # --------- AFTER WE SEPARATED BOF AND EOF, STICK EVERYTHING TOGETHER
                
                complete_data_frame = complete_data_frame + arq_frame_payload
                
            
        #check if Begin of Frame BOF and End of Frame EOF are received, then start calculating CRC and sticking everything together
        if static.ARQ_FRAME_BOF_RECEIVED == True and static.ARQ_FRAME_EOF_RECEIVED == True:
        
            frame_payload_crc = helpers.get_crc_16(complete_data_frame)
          
            #IF THE FRAME PAYLOAD CRC IS EQUAL TO THE FRAME CRC WHICH IS KNOWN FROM THE HEADER --> SUCCESS      
            if frame_payload_crc == static.FRAME_CRC:
                 logging.info("ARQ | RX | DATA FRAME SUCESSFULLY RECEIVED! - TIME TO PARTY")
                 
                 static.RX_BUFFER.append(complete_data_frame)
                 
                 # clearing buffers and resetting counters
                 static.ARQ_RX_BURST_BUFFER = []
                 static.ARQ_RX_FRAME_BUFFER = []
                 static.ARQ_FRAME_BOF_RECEIVED = False
                 static.ARQ_FRAME_EOF_RECEIVED = False
                 #static.ARQ_N_RX_ARQ_FRAMES = 0
                 static.ARQ_N_ARQ_FRAMES_PER_DATA_FRAME = 0
                 
                 print("----------------------------------------------------------------")
                 print(static.RX_BUFFER[-1])
                 
                 print("----------------------------------------------------------------")
                 # HERE: WE COULD SEND ACK FOR TOTAL FRAME                  
            else:
                logging.info("ARQ | RX | DATA FRAME NOT SUCESSFULLY RECEIVED!")


def ack_received():
    
    logging.info("ARQ | RX | ACK RCVD!")
    static.ARQ_ACK_TIMEOUT = 1 #Force timer to stop waiting
    static.ARQ_ACK_RECEIVED = 1 #Force data loops of TNC to stop and continue with next frame


def transmit(data_out):

            static.ARQ_PAYLOAD_PER_FRAME = static.FREEDV_DATA_PAYLOAD_PER_FRAME - 8 #3 ohne ARQ_TX_N_FRAMES_PER_BURST  
            frame_header_length = 4
                          
            n_arq_frames_per_data_frame = (len(data_out)+frame_header_length) // static.ARQ_PAYLOAD_PER_FRAME + ((len(data_out)+frame_header_length) % static.ARQ_PAYLOAD_PER_FRAME > 0) # aufrunden 3.2 = 4
            
            #print(static.FREEDV_DATA_PAYLOAD_PER_FRAME)
            #print(static.ARQ_PAYLOAD_PER_FRAME)
            #print(n_bursts_prediction)
            ####static.ARQ_N_ARQ_FRAMES_PER_DATA_FRAME = n_arq_frames_per_data_frame.to_bytes(2, byteorder='big') #65535
            
            frame_payload_crc = helpers.get_crc_16(data_out)
            #print(frame_payload_crc)
            
            # This is the total frame with frame header, which will be send
            data_out =  frame_payload_crc + static.FRAME_BOF + data_out + static.FRAME_EOF
            #                     2                 2              N           2

            
            # --------------------------------------------- LETS CREATE A BUFFER BY SPLITTING THE FILES INTO PEACES
            static.TX_BUFFER = [data_out[i:i+static.ARQ_PAYLOAD_PER_FRAME] for i in range(0, len(data_out), static.ARQ_PAYLOAD_PER_FRAME)]
            static.TX_BUFFER_SIZE = len(static.TX_BUFFER)
            #print(static.TX_BUFFER)
            
            logging.info("ARQ | TX | DATA FRAME --- BYTES: " + str(len(data_out)) + " ARQ FRAMES: " + str(static.TX_BUFFER_SIZE))
                      
            # --------------------------------------------- THIS IS THE MAIN LOOP-----------------------------------------------------------------
   
            static.ARQ_N_SENT_FRAMES = 0 # SET N SENT FRAMES TO 0 FOR A NEW SENDING CYCLE
            while static.ARQ_N_SENT_FRAMES <= static.TX_BUFFER_SIZE:

                #print("static.ARQ_N_SENT_FRAMES: " + str(static.ARQ_N_SENT_FRAMES))
                static.ARQ_TX_N_FRAMES_PER_BURST = get_n_frames_per_burst()
                           
                # ----------- CREATE FRAME TOTAL PAYLOAD TO BE ABLE TO CREATE CRC FOR IT
                burst_total_payload = bytearray()
                try: # DETECT IF LAST BURST TO PREVENT INDEX ERROR OF BUFFER
                    for i in range(static.ARQ_TX_N_FRAMES_PER_BURST): # Loop through TX_BUFFER LIST
                    
                        # make sure we have always a filled buffer with the length of payload per frame
                        burst_raw_payload = static.TX_BUFFER[static.ARQ_N_SENT_FRAMES + i] 
                        burst_payload = bytearray(static.ARQ_PAYLOAD_PER_FRAME) 
                        burst_payload[:len(burst_raw_payload)] = burst_raw_payload # get frame from TX_BUFFER     
                        burst_total_payload = burst_total_payload + burst_payload # append single frame to total payload buffer
                                    
                except IndexError: # IF LAST BURST DETECTED BUILD CRC WITH LESS FRAMES AND SET static.ARQ_TX_N_FRAMES_PER_BURST TO VALUE OF REST!
                     
                     burst_total_payload = bytearray() # reset burst_total_payload because of possible input remaining of detecting loop one step above
                     if static.ARQ_N_SENT_FRAMES == 0  and (static.ARQ_TX_N_FRAMES_PER_BURST > static.TX_BUFFER_SIZE): #WE CANT DO MODULO 0 --> CHECK IF FIRST FRAME == LAST FRAME
                          static.ARQ_TX_N_FRAMES_PER_BURST = static.TX_BUFFER_SIZE
                     elif static.ARQ_N_SENT_FRAMES == 1 and (static.ARQ_TX_N_FRAMES_PER_BURST > static.TX_BUFFER_SIZE): # MODULO 1 WILL ALWAYS BE 0 --> THIS FIXES IT
                            static.ARQ_TX_N_FRAMES_PER_BURST = static.TX_BUFFER_SIZE - static.ARQ_N_SENT_FRAMES  
                     else:
                         static.ARQ_TX_N_FRAMES_PER_BURST = (static.TX_BUFFER_SIZE % static.ARQ_N_SENT_FRAMES)

                     #print("ARQ_TX_N_FRAMES_PER_BURST OF LAST BURST: " + str(static.ARQ_TX_N_FRAMES_PER_BURST))
                     
                     for i in range(static.ARQ_TX_N_FRAMES_PER_BURST): #bytearray(b'111111111111111111111111222222222222222222222222')
                        
                        # make sure we have always a filled buffer with the length of payload per frame
                        burst_raw_payload = static.TX_BUFFER[static.ARQ_N_SENT_FRAMES + i] 
                        burst_payload = bytearray(static.ARQ_PAYLOAD_PER_FRAME) 
                        burst_payload[:len(burst_raw_payload)] = burst_raw_payload # get frame from TX_BUFFER     
                        burst_total_payload = burst_total_payload + burst_payload # append single frame to total payload buffer
                                       
                # ----------- GENERATE PAYLOAD CRC FOR ARQ_TX_N_FRAMES_PER_BURST               
                static.ARQ_BURST_PAYLOAD_CRC = helpers.get_crc_16(burst_total_payload)
                
                #--------------------------------------------- N ATTEMPTS TO SEND BURSTS IF ACK RECEPTION FAILS
                for static.TX_N_RETRIES in range(static.TX_N_MAX_RETRIES):
                    logging.info("ARQ | TX | ARQ FRAME --- ATTEMPT [" + str(static.TX_N_RETRIES+1) + "/" + str(static.TX_N_MAX_RETRIES) + "]")
                    # lets start a thread to transmit nonblocking
                    TRANSMIT_ARQ_BURST_THREAD = threading.Thread(target=modem.transmit_arq_burst, name="TRANSMIT_ARQ_BURST")
                    TRANSMIT_ARQ_BURST_THREAD.start()
                    
                    # lets wait during sending. After sending is finished we will continue
                    while static.ARQ_STATE == 'SENDING_DATA':
                        time.sleep(0.05)
                        
                        
                    # --------------------------- START TIMER FOR WAITING FOR ACK ---> IF TIMEOUT REACHED, ACK_TIMEOUT = 1
                                        #reset timer and ack state
                    static.ARQ_ACK_RECEIVED = 0
                    static.ARQ_ACK_TIMEOUT = 0
                    
                    logging.info("ARQ | RX | WAITING FOR ACK")
                    static.ARQ_STATE = 'RECEIVING_ACK'
                                        
                    timer = threading.Timer(static.ARQ_ACK_TIMEOUT_SECONDS, arq_ack_timeout)
                    timer.start() 


                    # --------------------------- WHILE TIMEOUT NOT REACHED AND NO ACK RECEIVED --> LISTEN
                    while static.ARQ_ACK_TIMEOUT == 0 and static.ARQ_ACK_RECEIVED == 0:                 
                        time.sleep(0.01) # lets reduce CPU load a little bit
                        #print(static.ARQ_STATE)
                                           
                        #--------------- BREAK LOOP IF ACK HAS BEEN RECEIVED
                    if static.ARQ_ACK_RECEIVED == 1:                        
                        #-----------IF ACK RECEIVED, INCREMENT ITERATOR FOR MAIN LOOP TO PROCEED WITH NEXT FRAMES/BURST
                        static.ARQ_N_SENT_FRAMES = static.ARQ_N_SENT_FRAMES + static.ARQ_TX_N_FRAMES_PER_BURST
                        break
                        
                    if static.ARQ_ACK_RECEIVED == 0 and static.ARQ_ACK_TIMEOUT == 1:
                        #logging.info("ARQ | RX | ACK TIMEOUT | SENDING ARQ BURST AGAIN")
                        pass
                 
                 
                 
                # ----------- if no ACK received and out of retries.....stop frame sending
                if static.ARQ_ACK_RECEIVED == 0 and static.ARQ_ACK_TIMEOUT == 1:
                        logging.info("ARQ | TX | NO ACK RECEIVED | DATA FRAME NEEDS TO BE RESEND!")
                        break


                #-------------------------BREAK TX BUFFER LOOP IF ALL PACKETS HAVE BEEN SENT
                if static.ARQ_N_SENT_FRAMES == static.TX_BUFFER_SIZE:    
                    break 
               
                
                # ------------ TIMER TO WAIT UNTIL NEXT PACKAGE WILL BE SEND TO PREVENT TIME ISSEUS --> NEEDS TO BE IMPROVED LATER
                #time.sleep(3)
                        
            # IF TX BUFFER IS EMPTY / ALL FRAMES HAVE BEEN SENT --> HERE WE COULD ADD AN static.VAR for IDLE STATE    
            #logging.info("ARQ | TX | FRAME SUCESSFULLY TRANSMITTED! - TIME TO PARTY")
            logging.info("ARQ | TX | BUFFER EMPTY")
            #print(static.ARQ_N_SENT_FRAMES)
            #print(static.ARQ_TX_N_FRAMES_PER_BURST)
            # - RESET COUNTERS
            static.ARQ_N_SENT_FRAMES = 0
            static.ARQ_TX_N_FRAMES_PER_BURST = 0
            static.ARQ_ACK_RECEIVED = 0
            
           
# BURST MACHINE TO DEFINE N BURSTS PER FRAME    ---> LATER WE CAN USE CHANNEL MESSUREMENT TO SET FRAMES PER BURST         
def get_n_frames_per_burst():
 
    n_frames_per_burst = randrange(1,15)
    #n_frames_per_burst = 1          
    return n_frames_per_burst
