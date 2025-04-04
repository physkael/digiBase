#! /bin/env python3

#Copyright (c) 2024 Kael Hanson (kael.hanson@gmail.com)

"""
digibase.py - Simple DAQ for ORTEC/AMETEK digiBase
---------------------------------------------------

This module provides a simple interface to the ORTEC/AMETEK digiBASE,
a combined PMT base and data acquisition front-end. The digiBASE and
digiBASE-RH are USB devices.

The main control surface is an 80-byte status register that is
accessed in this class as a 640-bit register. Known subfields are:

    0       Acquisition mode (1 = PHA, 0 = list mode acquisition)
    1       Start/stop acquisition (1 = start, 0 = stop)
    2       Enable livetime preset
    3       Enable realtime preset  
    4       Automatic gain stabilization enable/disable
    5       Automatic zero stabilization enable/disable
    6       HV enable
    7       Reserved/unknown
    8       Busy collecting data
    9       Enable input status
    10      Waveform ready
    11      HV readback ADC busy
    12      Reserved
    13:14   HV readback - high 2 bits
    15      Reserved
    16:23   Pulse width
    24:32   HV readback - low 8 bits
    40:47   Reserved
    48:55   Reserved
    56:63   External gate mode (0 = off, 1 = coincidence, 3 = enabled)
    96:120  Fine gain readback
    128:152 Fine gain set
    192:224 Livetime preset
    224:256 Livetime counter
    256:288 Realtime preset
    288:320 Realtime counter
    320:336 Should be 0x03ff - number of MCA channels
    336:352 HV setpoint (1.25 V increments)
    608     Clear counters
"""

import usb.core
import usb.util
from array import array
import sys, os
from argparse import ArgumentParser
from time import sleep
from datetime import datetime, timedelta
import numpy as np
from struct import pack, unpack
import logging
from enum import Enum

__version__ = '0.3.4'

# FIX THIS - I followed what libdbaseRH was doing
# and it's really convoluted. 
STAT_1 = b'\x00\x83\x00\x0c\x20\x00\x30\x20' + \
         b'\x03\x00\x00\x00\x00\x0a\x00\x00' + \
         b'\x00\x00\x00\xa0\x00\x00\x28\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\xff\x03\x80\x02\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x5e\x01\x2c\x01\xfa\x00\x00' + \
         b'\x00\x00\x80\x9e\x00\x85\x00\x6c' + \
         b'\x00\x40\x00\x00\x00\x10\x0c\x24\x00'

STAT_2 = b'\x00\x01\x00\x0c\x20\x00\x30\x20' + \
         b'\x03\x00\x00\x00\x00\x0a\x00\x00' + \
         b'\x00\x00\x00\x20\x00\x00\x28\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\xff\x03\x80\x02\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x5e\x01\x2c\x01\xfa\x00\x00' + \
         b'\x00\x00\x00\x9e\x00\x85\x00\x6c' + \
         b'\x00\x40\x00\x00\x00\x00\x0c\x24\x00'

STAT_3 = b'\x00\x01\x00\x0c\x20\x00\x30\x20' + \
         b'\x03\x00\x00\x00\x00\x0a\x00\x00' + \
         b'\x00\x00\x00\x20\x00\x00\x28\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\xff\x03\x80\x02\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x5e\x01\x2c\x01\xfa\x00\x00' + \
         b'\x00\x00\x00\x9e\x00\x85\x00\x6c' + \
         b'\x00\x40\x00\x00\x00\x01\x0c\x24\x00'

STAT_4 = b'\x00\x01\x00\x0c\x20\x00\x30\x20' + \
         b'\x03\x00\x00\x00\x00\x0a\x00\x00' + \
         b'\x00\x00\x00\x20\x00\x00\x28\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\xff\x03\x80\x02\x00\x00\x00' + \
         b'\x00\x00\x00\x00\x00\x00\x00\x00' + \
         b'\x00\x5e\x01\x2c\x01\xfa\x00\x00' + \
         b'\x00\x00\x00\x9e\x00\x85\x00\x6c' + \
         b'\x00\x40\x00\x00\x00\x04\x0c\x24\x00'

# For non-RH style bases - Q&D fix this 
STAT_5 = {
    1  : 0x83,  3: 0x0c,  6: 0x30,  7: 0x20,  8: 0x03,
    13 : 0x0a, 18: 0x00, 19: 0xa0, 21: 0xb0, 22: 0x1e,
    41 : 0xff, 42: 0x03, 43: 0x58, 44: 0x02, 57: 0xfa,
    58 : 0x01, 59: 0xd5, 60: 0x01, 61: 0xb0, 62: 0x01,
    66 : 0x80, 67: 0xfa, 68: 0x01, 69: 0xd5, 70: 0x01,
    71 : 0xb0, 72: 0x01, 73: 0x40, 77: 0x10, 79: 0x2e,
    80 : 0x0b
}

STAT_6 = {
    1 : 0x01,  3: 0x0c,  6: 0x30,  7: 0x20,  8: 0x03,
    13: 0x0a, 18: 0x00, 19: 0x20, 21: 0xb0, 22: 0x1e,
    41: 0xff, 42: 0x03, 43: 0x58, 44: 0x02, 57: 0xfa,
    58: 0x01, 59: 0xd5, 60: 0x01, 61: 0xb0, 62: 0x01,
    67: 0xfa, 68: 0x01, 69: 0xd5, 70: 0x01, 71: 0xb0,
    72: 0x01, 73: 0x40, 79: 0x2e, 80: 0x0b
}

def dict_to_status(dst):
    status = array('B', [0]*80)
    for key, val in dst.items():
        status[key-1] = val
    return status.tobytes()


class bit_register:
    def __init__(self, val=0):
        self.reg = val

    def __getitem__(self, idx):
        if isinstance(idx, int):
            return (self.reg >> idx) & 1
        if isinstance(idx, slice):
            len = idx.stop - idx.start
            mask = (1 << len) - 1
            return (self.reg >> idx.start) & mask
        
    def __setitem__(self, idx, val):
        if isinstance(idx, int):
            mask = 1 << idx
            self.reg = (self.reg & ~mask) | (val << idx)
        if isinstance(idx, slice):
            len = idx.stop - idx.start
            mask = (1 << len) - 1
            self.reg = (self.reg & ~(mask << idx.start)) | (val << idx.start)

class ExtGateMode(Enum):
    OFF = 0
    COINCIDENCE = 1
    ENABLED = 3

class digiBase:
    VENDOR_ID: int  = 0x0a2d

    def __init__(self, serialNumber=None):

        self.log = logging.getLogger('digiBase')
        self.dev = None

        if serialNumber is None:
            self.dev = usb.core.find(idVendor=digiBase.VENDOR_ID)
        else:
            # Find all devices and match serial number
            if not isinstance(serialNumber, str): serialNumber = str(serialNumber)
            for dev in usb.core.find(idVendor=digiBase.VENDOR_ID, find_all=True):
                sn = dev.serial_number.strip('\x00')
                self.log.debug(f'Bus {dev.bus:03d} Device {dev.address:03d}: '
                               f'ID {dev.idVendor:04x}:{dev.idProduct:04x} '
                               ' S/N', sn)
                if sn == serialNumber:
                    self.dev = dev
                    break

        if self.dev is None: raise ValueError("Device not found")
        self.log.info(f'Found ORTEC digiBase device {self.dev.idVendor:04x}:{self.dev.idProduct:04x}')
        self.isRH = self.dev.idProduct == 0x001f

        self.dev.reset()
        self.dev.set_configuration()
        self.serial = usb.util.get_string(self.dev, self.dev.iSerialNumber).rstrip('\x00')
        cfg = self.dev.get_active_configuration()

        # Determine whether device needs firmware bitstream 
        if self.isRH:
            # Write out a START (0x06, 0x00, 0x02, 0x00)
            r = self.send_command(b'\x06\x00\x02\x00', init=True)
            needs_init = (r[0] == 4 and r[1] == 0x80)
        else:
            r = self.send_command(b'\x06')
            needs_init = (r[0] == 0)

        if needs_init:
            firmware_path = self._find_firmware()
            with open(firmware_path, 'rb') as f:
                fw = f.read()
            if self.isRH:
                # Firmware configuration needed - write a START2 packet
                self.send_command(b'\x04\x00\x02\x00', init=True)
                self.log.info('Loading digiBase RH firmware')
                for page in (fw[:61424], fw[61424:75463]):
                    self.send_command(b'\x05\x00\x02\x00' + page, init=True)
                self.send_command(b'\x06\x00\x02\x00', init=True)
                self.send_command(b'\x11\x00\x02\x00', init=True)
                # STATUS init
                self.send_command(STAT_1)
                self.send_command(STAT_2)
                self.send_command(STAT_2)
                self.send_command(b'\x04')
                self.send_command(STAT_3)
                self.send_command(STAT_2)
                self.send_command(STAT_2)
                # This may signal end of initialization
                r = self.send_command(b'\x12\x00\x06\x00', init=True)
                self.log.debug('End of Init Message: ' + str(r))
                self.send_command(STAT_2)
                self.send_command(STAT_4)
            else:
                self.send_command(b'\x04')
                self.log.info('Loading firmware')
                r = self.send_command(b'\x05' + fw[0:61438])
                self.log.debug(f'FW1: {r[0]}')
                self.send_command(b'\x05' + fw[61438:122877], no_read=True)
                # Intentional NULL byte sent
                r = self.send_command(b'')
                self.log.debug(f'FW2: {r[0]}')
                r = self.send_command(b'\x05' + fw[122877:166965])
                self.log.debug(f'FW3: {r[0]}')
                r = self.send_command(b'\x06')
                self.log.debug(f'Post-FW START:{r[0]}')
                r = self.send_command(b'\x00' + dict_to_status(STAT_5))
                self.log.debug(f'STAT_5: {r[0]}')
                r = self.send_command(b'\x00' + dict_to_status(STAT_6))
                self.log.debug(f'STAT_6: {r[0]}')
                STAT_6[77] = 1
                r = self.send_command(b'\x00' + dict_to_status(STAT_6))
                self.log.debug(f'STAT_6[77] = 1: {r[0]}')
                STAT_6[77] = 0
                r = self.send_command(b'\x00' + dict_to_status(STAT_6))
                self.log.debug(f'STAT_6[77] = 0: {r[0]}')
                STAT_6[1]  &= 0xf3
                r = self.send_command(b'\x00' + dict_to_status(STAT_6))
                self.log.debug(f'STAT_6[1] &= 0xf3: {r[0]}')

            self.clear_spectrum()
        else:
            # No firmware config needed
            self.read_status_register()
          
            # Set CNT byte
            self._status[610] = 0
            self.write_status_register()
            self._status[610] = 1
            self.write_status_register()
        
        self.read_status_register()

    def _find_firmware(self):
        from pathlib import Path
        key = 'DIGIBASE_FIRMWARE_PATH'
        search = os.environ[key].split(':') if key in os.environ else \
            [os.path.expanduser('~/.digiBase'), '.']
        for p in search:
            path_to_fw = Path(p) / ('digiBase' + ('RH' if self.isRH else '') + '.rbf')
            if path_to_fw.is_file(): return path_to_fw
        raise RuntimeError("Unable to find digiBase Firmware")
        
    def read_status_register(self):
        self._status = bit_register(
            int.from_bytes(
                self.send_command(b'\x01', init=False), 
                byteorder='little'
            )
        )

    def write_status_register(self):
        resp = self.send_command(
            b'\x00' + self._status.reg.to_bytes(80, byteorder='little')
        )
        return resp
        #assert len(resp) == 0

    def clear_spectrum(self):
        self.send_command(b'\x02' + b'\x00'*4096)

    def clear_counters(self):
        "Clear livetime and realtime counters"
        self._status[608] = 1
        self.write_status_register()
        self._status[608] = 0
        self.write_status_register()

    def send_command(
            self, 
            cmd, 
            init:bool=False, 
            max_length:int=80,
            no_read=False):
        if self.isRH:
            epID = (0x01, 0x81) if init else (0x08, 0x82)
        else:
            epID = (0x02, 0x82)
        n = self.dev.write(epID[0], cmd, timeout=1000)
        self.log.debug(f"Wrote {n} bytes to endpoint {epID[0]:02x}")
        if n != len(cmd): raise IOError("Incomplete write")
        if no_read: return array('B')
        resp = self.dev.read(epID[1], max_length, timeout=125)
        self.log.debug(f"Read {len(resp)} bytes from endpoint {epID[1]:02x}")
        return resp
            
    def start(self):
        "Start the acquisition"
        self._status[1] = 1
        self.write_status_register()

    def stop(self):
        "Stop the acquisition"
        self._status[1] = 0
        self.write_status_register()

    def print_status(self):
        srbytes = array('B', self._status.reg.to_bytes(80, byteorder='little'))
        for (i, a) in enumerate(srbytes):
            print(f'{a:02x}', end=' ')
            if i%16 == 15: print(' ')

    @property
    def livetime(self) -> float:
        "Acquisition livetime, in seconds"
        self.read_status_register()
        return self._status[224:256] / 50
    
    @property
    def livetime_preset(self) -> float:
        "Acquisition livetime limit, in seconds"
        self.read_status_register()
        return self._status[192:224] / 50
    
    @livetime_preset.setter
    def livetime_preset(self, val: float):
        self._status[192:224] = int(val * 50) & 0xffff_ffff
        self.write_status_register()
    
    @property
    def realtime(self) -> float:
        self.read_status_register()
        return self._status[288:320] / 50

    @property
    def realtime_preset(self) -> float:
        self.read_status_register()
        return self._status[256:288] / 50
    
    @realtime_preset.setter
    def realtime_preset(self, val: float):
        self._status[256:288] = int(val * 50) & 0xffff_ffff
        self.write_status_register()

    @property
    def spectrum(self):
        resp = self.send_command(b'\x80', max_length=5000)
        return unpack('1024I', resp)
    
    @property
    def hits(self):
        resp = self.send_command(b'\x80', max_length=132_000)
        n = len(resp) // 4
        return unpack(f'{n}I', resp)

    @property
    def hv_enabled(self):
        self.read_status_register()
        return bool(self._status[6])
    
    @hv_enabled.setter
    def hv_enabled(self, val: bool):
        self._status[6] = 1 if val else 0
        self.write_status_register

    @DeprecationWarning
    def enable_hv(self):
        self._status[6] = 1
        self.write_status_register()
        
    @DeprecationWarning
    def disable_hv(self):
        self._status[6] = 0
        self.write_status_register()

    @property
    def hv(self) -> float:
        self.read_status_register()
        return self._status[336:352] * 5 / 4
    
    @hv.setter
    def hv(self, val):
        val = int(val)
        if val >= 1200: raise ValueError(f"{val} > Max HV 1200V")
        val = (val * 4) // 5
        self._status[336:352] = val
        self.write_status_register()

    @property
    def pw(self):
        self.read_status_register()
        return 0.0625 * (self._status[16:24] - 12) + 0.75

    @pw.setter
    def pw(self, val):
        if val < 0.75 or val > 2.0: raise ValueError("Pulse width out of range")
        val = 16 * (val - 0.75) + 12
        self._status[16:24] = val
        self.write_status_register()

    @property
    def hv_readback(self):
        # Trigger HV ADC read
        self._status[610] = 0
        self.write_status_register()
        self._status[610] = 1
        self.write_status_register()
        sleep(0.01)
        self.read_status_register()
        return (self._status[24:32] | (self._status[13:15] << 8)) * 1.25
    
    @property
    def lld(self):
        "Lower level discriminator"
        self.read_status_register()
        return self._status[170:180]
    
    @lld.setter
    def lld(self, val):
        val &= 0x3ff
        self._status[170:180] = val
        self.write_status_register()
    
    @property
    def uld(self):
        "Upper level discriminator"
        self.read_status_register()
        return self._status[176:192]
    
    @property
    def fine_gain(self) -> float:
        self.read_status_register()
        return self._status[96:128] / 0x400000
    
    @fine_gain.setter
    def fine_gain(self, val: float):
        if val < 0.25 or val >= 2.0:
            raise ValueError("Fine gain out of range [0.25, 2.0)")
        # The fine gain really does appear to be a 23-bit value
        val = int(val * 0x400000)
        # Set high bit to 1 to active register write
        # On read the bit should be cleared
        self._status[128:152] = val | 0x800000
        self.write_status_register()

    @uld.setter
    def uld(self, val):
        val &= 0xffff
        self._status[176:192] = val
        self.write_status_register()

    @property
    def ext_gate(self) -> ExtGateMode:
        self.read_status_register()
        return ExtGateMode(self._status[56:64])
    
    @ext_gate.setter
    def ext_gate(self, mode: ExtGateMode):
        self._status[56:64] = mode.value
        self.write_status_register()

    def auto_stabilize(self, gain: tuple=None, zero: tuple=None):
        """ 
        Enable / disable internal gain and zero/offset stabilization.
        Manual says this is to correct for temperature-related drifts.
        Use with caution.

        Parameters
        ----------
        gain : list
            (hi_ch, center_ch, lo_ch) tuple or None for gain stabilization
        zero : list
            (hi_ch, center_ch, lo_ch) tuple or None for zero stabilization
        """
        self._status[4:6] = 0
        if gain is not None and isinstance(gain, (tuple,list)) and len(gain) == 3:
            self._status[4] = 1
            self._status[448:464] = gain[0]
            self._status[464:480] = gain[1]
            self._status[480:496] = gain[2]
        if zero is not None and isinstance(zero, (tuple,list)) and len(zero) == 3:
            self._status[5] = 1
            self._status[528:544] = zero[0]
            self._status[544:560] = zero[1]
            self._status[560:576] = zero[2]
        self.write_status_register()

    def set_presets(self, livetime: bool=False, realtime: bool=False):
        """
        Set / reset livetime and realtime presets.
        The DBASE will stop acquisition when either preset is reached.
        The livetime and realtiem preset values are set elsewhere.
        """
        self._status[2] = 1 if livetime else 0
        self._status[3] = 1 if realtime else 0
    
    def set_acq_mode_list(self):
        self._status[0:2] = 0
        self._status[7] = 1
        self._status[608] = 1
        self.write_status_register()
        self._status[7] = 0
        self._status[608] = 0
        self.write_status_register()

    def set_acq_mode_pha(self):
        self._status[0] = 1
        self.write_status_register()

    def __del__(self):
        self.log.debug('Closing device')
        if self.dev is not None:
            usb.util.release_interface(self.dev, 0)
            usb.util.dispose_resources(self.dev)


def write_background(filename, s:np.ndarray, exposure:float, comment:str):
    with open(filename, 'wb') as f:
        f.write(b'DBKG\x00\x00\x00\x00')
        f.write(pack('d', datetime.now().timestamp()))
        f.write(pack('d', exposure))
        if comment is None:
            f.write(b'\x00'*64)
        else:
            f.write(comment.encode('utf-8')[:63].ljust(64, b'\x00'))
        s.tofile(f)

def read_background(filename) -> tuple[np.ndarray, float, float, str]:
    with open(filename, 'rb') as f:
        if f.read(8) != b'DBKG\x00\x00\x00\x00': raise ValueError("Unknown file format")
        t, exp = unpack('2d', f.read(16))
        comment = f.read(64).decode('utf-8')
        s = np.fromfile(f, dtype=np.int32)
        return s, t, exp, comment
    
if __name__ == "__main__":
    parser = ArgumentParser(prog='digibase.py', description='Simple DAQ for ORTEC/AMETEK digiBase')
    parser.add_argument('--pmt-hv', type=int, default=800)
    parser.add_argument('--disc', type=int, default=20)
    parser.add_argument('-X', '--external-gate', default='OFF', choices=['OFF', 'COINCIDENCE', 'ENABLED'])
    parser.add_argument('-g', '--gain', type=float, default=0.5)
    parser.add_argument('--realtime-preset', type=float, default=0.0)
    parser.add_argument('--livetime-preset', type=float, default=0.0)
    parser.add_argument('--sn', help='S/N of digiBase (in case of >1)')
    parser.add_argument('-q', '--quiet', action='store_true')
    parser.add_argument('-L', '--log-level', nargs='?', default='WARNING', const='INFO')

    subparsers = parser.add_subparsers(dest='command', help='Run modes')
    parser_spe = subparsers.add_parser('spect', help='Acquire spectrum, write to file')
    parser_spe.add_argument('duration', type=float, help='Time, in seconds to integrate spectrum')
    parser_spe.add_argument('filename', help='Output file in which spectrum is saved')
    parser_spe.add_argument('-m', '--comment', help='Short run description (max 63 char)')

    parser_det = subparsers.add_parser('detect', help='Detect presence of signal over background')
    parser_det.add_argument('duration', type=float, help='Integration time of each query interval')
    parser_det.add_argument('n', type=int, help='Number of intervals')
    parser_det.add_argument('sig0', type=int, help='Channel # of low side of signal RoI')
    parser_det.add_argument('sig1', type=int, help='Channel # of high side of signal RoI')
    parser_det.add_argument('filename', nargs='+', help='Spectrum file for background subtraction')
    parser_det.add_argument('-a', '--alpha', type=float, help='Exponential Moving Average parameter.')
    parser_det.add_argument('--norm-roi')

    parser_acq = subparsers.add_parser('acq', help='List mode acquisition')
    parser_acq.add_argument('duration', type=float, help='Acquisition time')
    parser_acq.add_argument('filename', help='Output file for list mode data')
    
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level)
    log = logging.getLogger()

    base = digiBase(args.sn)

    # Configure the device to sane defaults    
    base.clear_spectrum()
    base.clear_counters()
    
    base.livetime_preset = args.livetime_preset
    base.realtime_preset = args.realtime_preset
    base.set_presets(livetime=args.livetime_preset > 0, realtime=args.realtime_preset > 0)

    base.lld = args.disc
    base.ext_gate = ExtGateMode[args.external_gate]

    # Disable auto gain and zero stabilization
    base.auto_stabilize()

    # HV and gain settings
    if base.hv != args.pmt_hv: base.hv = args.pmt_hv
    if not base.hv_enabled: 
        base.hv_enabled = True
        sleep(5.0)
    base.fine_gain = args.gain

    if args.command == 'spect':
        base.set_acq_mode_pha()
        base.start()
        t0 = datetime.now()
        run_time = timedelta(seconds=args.duration)
        while (elapsed_time := datetime.now() - t0) < run_time:
            if not args.quiet: print("Elapsed time: " + str(elapsed_time), end='\r')
            sleep(0.1)
        base.stop()
        spectrum = np.array(base.spectrum, dtype=np.uint32)
        if not args.quiet: 
            print("Elapsed time: " + str(elapsed_time))
            print(f"Collected {np.sum(spectrum)} counts")
            print(f"Livetime {base.livetime:.3f} s")
            print(f"Realtime {base.realtime:.3f} s")
        write_background(args.filename, spectrum, base.livetime, args.comment)
    elif args.command == 'detect':
        base.set_acq_mode_pha()
        base.start()
        bkg = np.zeros(1024, dtype=np.int32)
        exp_bkg = 0.0
        for filename in args.filename:
            s, t_bkg, pex, comment = read_background(filename)
            bkg += s
            exp_bkg += pex
        
        # Normalize control to counts per bin per second
        bkg = bkg / exp_bkg
        log.debug(f'Total background counts after normalization {np.sum(bkg)}')
        log.debug(f'ROI background counts after normalization {np.sum(bkg[args.sig0:args.sig1])}')
        spectrum_last = np.zeros(1024, dtype=np.int32)
        livetime_last = 0.0
        counts = None

        # Optional mode normalizes not on exposure time but a portion of the spectrum
        norm_roi = None
        if args.norm_roi is not None:
            nr0, nr1 = args.norm_roi.split(',')
            norm_roi = (int(nr0), int(nr1))

        try:
            for i in range(args.n):
                sleep(args.duration)
                spectrum = np.array(base.spectrum, dtype=np.int32)
                livetime = base.livetime
                livetime_diff = livetime - livetime_last
                spectrum_diff = spectrum - spectrum_last
                cspec = np.sum(spectrum_diff)
                if norm_roi is not None:
                    bkg_norm = np.sum(bkg[norm_roi[0]:norm_roi[1]])
                    det_norm = np.sum(spectrum_diff[norm_roi[0]:norm_roi[1]])
                    bkg_sub = np.zeros(1024, dtype=np.int32)
                    if det_norm > 0:
                        bkg_sub = bkg_norm / det_norm * spectrum_diff - bkg
                else:
                    bkg_sub = spectrum_diff - bkg * livetime_diff
                spectrum_last = spectrum
                livetime_last = livetime
                c = np.sum(bkg_sub[args.sig0:args.sig1])
                craw = np.sum(spectrum_diff[args.sig0:args.sig1])
                counts = c if counts is None else c*args.alpha + counts*(1-args.alpha)
                print(datetime.now(), '-', f'cs: {cspec:.1f} craw {craw} counts {counts:.2f}', flush=True)
        except KeyboardInterrupt:
            print("User terminated run")
        base.stop()
    elif args.command == 'acq':
        nhits = 0
        with open(args.filename, 'wb') as fhits:
            base.set_acq_mode_list()
            base.start()
            t0 = datetime.now()
            run_time = timedelta(seconds=args.duration)
            fhits.write(b'DBLM\x00\x00\x00\x00')
            fhits.write(pack('d', t0.timestamp()))
            fhits.seek(16, os.SEEK_CUR)
            while (elapsed_time := datetime.now() - t0) < run_time:
                hits = base.hits
                nhits += len(hits)
                if len(hits) > 0: fhits.write(pack(f'{len(hits)}I', *hits))
                if not args.quiet: print("Elapsed time: " + str(elapsed_time), end='\r')
            base.stop()
            if not args.quiet: print("Elapsed time: " + str(elapsed_time))
            fhits.seek(16, os.SEEK_SET)
            fhits.write(pack('d', base.livetime))
            fhits.write(pack('d', base.realtime))
        if not args.quiet:
            print(f"Collected {nhits} hits")
            print(f"Livetime {base.livetime:.3f} s")
            print(f"Realtime {base.realtime:.3f} s")
