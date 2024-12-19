#! /bin/env python3

import usb.core
import usb.util
from array import array
import sys
from struct import pack, unpack
import logging

# FIX THIS - I followed what libdbaseRH was doing
# and it's really convoluted. 
STAT_1 = b'\x00\xb3\x00\x0c\x20\x00\x30\x20' + \
         b'\x03\x00\x00\x00\x00\x0a\x00\x00' + \
         b'\x00\x00\x00\xa0\x00\x00\x28\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\xff\x03\x80\x02\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x5e\x01\x2c\x01\xfa\x00\x00' + \
         b'\x00\x00\x80\x9e\x00\x85\x00\x6c' + \
         b'\x00\x40\x00\x00\x00\x10\x0c\x24\x00'

STAT_2 = b'\x00\x31\x00\x0c\x20\x00\x30\x20' + \
         b'\x03\x00\x00\x00\x00\x0a\x00\x00' + \
         b'\x00\x00\x00\x20\x00\x00\x28\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\xff\x03\x80\x02\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x5e\x01\x2c\x01\xfa\x00\x00' + \
         b'\x00\x00\x00\x9e\x00\x85\x00\x6c' + \
         b'\x00\x40\x00\x00\x00\x00\x0c\x24\x00'

STAT_3 = b'\x00\x31\x00\x0c\x20\x00\x30\x20' + \
         b'\x03\x00\x00\x00\x00\x0a\x00\x00' + \
         b'\x00\x00\x00\x20\x00\x00\x28\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\xff\x03\x80\x02\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x5e\x01\x2c\x01\xfa\x00\x00' + \
         b'\x00\x00\x00\x9e\x00\x85\x00\x6c' + \
         b'\x00\x40\x00\x00\x00\x01\x0c\x24\x00'

STAT_4 = b'\x00\x31\x00\x0c\x20\x00\x30\x20' + \
         b'\x03\x00\x00\x00\x00\x0a\x00\x00' + \
         b'\x00\x00\x00\x20\x00\x00\x28\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\xff\x03\x80\x02\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x5e\x01\x2c\x01\xfa\x00\x00' + \
         b'\x00\x00\x00\x9e\x00\x85\x00\x6c' + \
         b'\x00\x40\x00\x00\x00\x04\x0c\x24\x00'

class digiBaseRH:
    VENDOR_ID: int  = 0x0a2d
    PRODUCT_ID: int = 0x001f

    def __init__(self, serial_number: int=None):

        self.log = logging.getLogger('digiBaseRH')
        self.dev = usb.core.find(
            idVendor=digiBaseRH.VENDOR_ID, 
            idProduct=digiBaseRH.PRODUCT_ID
        )
        if self.dev is None: raise ValueError("Device not found")

        self.dev.reset()
        self.dev.set_configuration()
        self.serial = usb.util.get_string(self.dev, self.dev.iSerialNumber).rstrip('\x00')
        cfg = self.dev.get_active_configuration()

        # Determine whether device needs firmware bitstream 
        # Write out a START (0x06, 0x00, 0x02, 0x00)
        r = self.send_command(b'\x06\x00\x02\x00', init=True)
        if r[0] == 4 and r[1] == 0x80:
            # Firmware configuration needed - write a START2 packet
            self.send_command(b'\x04\x00\x02\x00', init=True)
            self.log.info('Loading firmware')
            with open('./digiBaseRH.rbf', 'rb') as f:
                fw = f.read()
            for page in (fw[:61424], fw[61424:75463]):
                self.send_command(b'\x05\x00\x02\x00' + page, init=True)
            self.send_command(b'\x06\x00\x02\x00', init=True)
            self.send_command(b'\x11\x00\x02\x00', init=True)

            self.send_command(STAT_1)
            self.send_command(STAT_2)
            self.send_command(STAT_2)
            self.send_command(b'\x04')
            self.send_command(STAT_3)
            self.send_command(STAT_2)
            self.send_command(STAT_2)
            self.clear_spectrum()

            # This may signal end of initialization
            r = self.send_command(b'\x12\x00\x06\x00', init=True)
            self.log.debug('End of Init Message: ' + str(r))

            self.send_command(STAT_2)
            self.send_command(STAT_4)

            self.read_status_register()
        elif r[0] == 0 and r[1] == 0:
            # No firmware config - get config 3x
            for i in range(3):
                self.read_status_register()
                
            r = self.send_command(b'\x12\x00\x06\x00', init=True)
            self.log.debug('End of Init Message: ' + str(r))
            
            # Set CNT byte
            self._sreg &= ~(1 << 610)
            self.write_status_register()
            self._sreg |= (1 << 610)
            self.write_status_register()
            self.read_status_register()
        
    def read_status_register(self):
        self._sreg = int.from_bytes(
            self.send_command(b'\x01', init=False), 
            byteorder='little'
        )

    def write_status_register(self):
        resp = self.send_command(
            b'\x00' + self._sreg.to_bytes(80, byteorder='little')
        )
        assert len(resp) == 0

    def clear_spectrum(self):
        self.send_command(b'\x02' + b'\x00'*4096)

    def send_command(self, cmd, init:bool=False, max_length:int=80):
        epID = (0x01, 0x81) if init else (0x08, 0x82)
        n = self.dev.write(epID[0], cmd, timeout=1000)
        self.log.debug(f"Wrote {n} bytes to endpoint {epID[0]:02x}")
        if n != len(cmd): raise IOError("Incomplete write")
        resp = self.dev.read(epID[1], max_length, timeout=125)
        self.log.debug(f"Read {len(resp)} bytes from endpoint {epID[1]:02x}")
        return resp
            
    def start(self):
        "Start the acquisition"
        self._sreg |= 2
        self.write_status_register()

    def stop(self):
        "Stop the acquisition"
        self._sreg &= ~(1 << 1)
        self.write_status_register()

    @property
    def spectrum(self):
        resp = self.send_command(b'\x80', max_length=5000)
        return unpack('1024I', resp)

    def enable_hv(self):
        if self.hv > 1200: 
            raise ValueError(f"HV setting {self.hv} exceeds max value.")
        self._sreg |= (1 << 6)
        self.write_status_register()
        
    def disable_hv(self):
        self._sreg &= ~(1 << 6)
        self.write_status_register()

    @property
    def hv(self):
        self.read_status_register()
        return ((self._sreg >> 336) & 0xffff) * 5 / 4
    
    @hv.setter
    def hv(self, val):
        if val >= 1200: raise ValueError(f"{val} > Max HV 1200V")
        val = (val * 4) // 5
        self._sreg &= ~(0xffff << 336)
        self._sreg |= (val << 336)
        self.write_status_register()

    @property
    def pw(self):
        return 0.0625 * (((self._sreg >> 16) & 0xff) - 12) + 0.75

    @pw.setter
    def pw(self, val):
        if val < 0.75 or val > 2.0: raise ValueError("Pulse width out of range")
        val = 16 * (val - 0.75) + 12
        self._sreg &= ~(0xff << 16)
        self._sred |= (val << 16)
        self.write_status_register()

    @property
    def hv_readback(self):
        self.read_status_register()
        return (self._sreg >> 24) & 0xffff
    
    def set_acq_mode_list(self):
        self._sreg |= 1
        self.write_status_register()

    def set_acq_mode_pha(self):
        self._sreg &= ~1
        self.write_status_register()

if __name__ == "__main__":
    from argparse import ArgumentParser
    from time import sleep
    import numpy as np
    
    parser = ArgumentParser(prog='digibase.py', description='Interface to ORTEC/AMETEK digiBase')
    parser.add_argument('--output')
    parser.add_argument('-f', '--firmware', default='digiBaseRH.rbf')
    parser.add_argument('-L', '--log-level', nargs='?', default='WARNING', const='INFO')
    parser.add_argument('--force-reload', action='store_true')
    parser.add_argument('-t', '--acq-time', type=float, default=10.0)
    parser.add_argument('-b', '--background')

    args = parser.parse_args()

    logging.basicConfig(level=args.log_level)
    log = logging.getLogger()

    base = digiBaseRH()
    base.hv = 800
    base.enable_hv()
    sleep(1.0)
    base.start()
    if args.background is not None:
    #    with open(args.background, 'rt') as f:
    #        line = f.readline()
    #        bkg_interval = float(line[6:])
        bkg = np.loadtxt(args.background)
        for i in range(10):
            s = np.array(base.spectrum, dtype=np.int32)
            diff = s - bkg
            print(f'Counts {np.sum(diff[27:36])}')
            base.clear_spectrum()
            sleep(args.acq_time)
    else:
        sleep(args.acq_time)
    base.stop()
    base.disable_hv()
    s = np.array(base.spectrum, dtype=np.int32)

    #with open(args.output, 'wt') as f:
    #    f.write(f'# INT {args.acq_time:.3f}')
    np.savetxt(args.output, s, fmt='%d')
