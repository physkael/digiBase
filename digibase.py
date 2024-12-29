#! /bin/env python3

#Copyright (c) 2024 Kael Hanson (kael.hanson@gmail.com)

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

# For non-RH style bases - Q&D fix this 
STAT_5 = {
    1  : 0xbd,  3: 0x0c,  6: 0x30,  7: 0x20,  8: 0x03,
    13 : 0x0a, 18: 0xb5, 19: 0xa9, 21: 0xb0, 22: 0x1e,
    41 : 0xff, 42: 0x03, 43: 0x58, 44: 0x02, 57: 0xfa,
    58 : 0x01, 59: 0xd5, 60: 0x01, 61: 0xb0, 62: 0x01,
    66 : 0x80, 67: 0xfa, 68: 0x01, 69: 0xd5, 70: 0x01,
    71 : 0xb0, 72: 0x01, 73: 0x40, 77: 0x10, 79: 0x2e,
    80 : 0x0b
}

STAT_6 = {
    1 : 0x3d,  3: 0x0c,  6: 0x30,  7: 0x20,  8: 0x03,
    13: 0x0a, 18: 0xb5, 19: 0x29, 21: 0xb0, 22: 0x1e,
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

    def __init__(self):

        self.log = logging.getLogger('digiBase')
        self.dev = usb.core.find(idVendor=digiBase.VENDOR_ID)

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
            if 'DBASE_FIRMWARE' in os.environ:
                firmware_path = os.environ['DBASE_FIRMWARE']
            else:
                firmware_path = './digiBase' + ('RH' if self.isRH else '') + '.rbf'
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
        return self._status[6]
    
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
        self.read_status_register()
        return self._status[24:40]
    
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
        return self._status[136:152] / 0x2000 * 0.5
    
    @fine_gain.setter
    def fine_gain(self, val: float):
        if val < 0.5 or val >= 2.0:
            raise ValueError("Fine gain out of range [0.5, 2.0)")
        val = int(val / 0.5 * 0x2000)
        self._status[136:152] = val
        self.write_status_register()

    @uld.setter
    def uld(self, val):
        val &= 0xffff
        self._status[176:192] = val
        self.write_status_register()

    def ext_gate(self, mode: ExtGateMode):
        self._status[56:64] = mode.value
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

    parser.add_argument('-L', '--log-level', nargs='?', default='WARNING', const='INFO')

    subparsers = parser.add_subparsers(dest='command', help='Run modes')
    parser_spe = subparsers.add_parser('spect', help='Acquire spectrum, write to file')
    parser_spe.add_argument('duration', type=float, help='Time, in seconds to integrate spectrum')
    parser_spe.add_argument('filename', help='Output file in which spectrum is saved')
    parser_spe.add_argument('-m', '--comment', help='Short run description (max 63 char)')

    parser_det = subparsers.add_parser('detect', help='Detect presence of signal over background')
    parser_det.add_argument('duration', type=float, help='Integration time of each query interval')
    parser_det.add_argument('n', type=int, help='Number of intervals')
    parser_det.add_argument('filename', help='Spectrum file for background subtraction')
    parser_det.add_argument('sig0', type=int, help='Channel # of low side of signal RoI')
    parser_det.add_argument('sig1', type=int, help='Channel # of high side of signal RoI')
    parser_det.add_argument('-a', '--alpha', type=float, help='Exponential Moving Average parameter.')

    parser_acq = subparsers.add_parser('acq', help='List mode acquisition')
    parser_acq.add_argument('duration', type=float, help='Acquisition time')
    parser_acq.add_argument('filename', help='Output file for list mode data')
    
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level)
    log = logging.getLogger()

    base = digiBase()

    # Configure the device to sane defaults    
    base.clear_spectrum()
    base.clear_counters()
    
    base.livetime_preset = args.livetime_preset
    base.realtime_preset = args.realtime_preset
    base.set_presets(livetime=args.livetime_preset > 0, realtime=args.realtime_preset > 0)

    base.lld = args.disc
    base.ext_gate(ExtGateMode[args.external_gate])

    # HV and gain settings
    if base.hv != args.pmt_hv: base.hv = args.pmt_hv
    if not base.hv_enabled: 
        base.hv_enabled = True
        sleep(5.0)
    base.fine_gain = args.gain

    if args.command == 'spect':
        base.set_acq_mode_pha()
        base.start()
        sleep(args.duration)
        base.stop()
        spectrum = np.array(base.spectrum, dtype=np.int32)
        print(f"Collected {np.sum(spectrum)} counts")
        print(f"Livetime {base.livetime:.3f} s")
        print(f"Realtime {base.realtime:.3f} s")
        write_background(args.filename, spectrum, args.duration, args.comment)
    elif args.command == 'detect':
        base.set_acq_mode_pha()
        base.start()
        bkg, t_bkg, exp_bkg, comment = read_background(args.filename)
        bkg = bkg * args.duration / exp_bkg
        spectrum_last = np.zeros(1024, dtype=np.int32)
        counts = None
        for i in range(args.n):
            sleep(args.duration)
            spectrum = np.array(base.spectrum, dtype=np.int32)
            spectrum_diff = spectrum - spectrum_last
            cspec = np.sum(spectrum_diff)
            bkg_sub = spectrum_diff - bkg
            spectrum_last = spectrum
            c = np.sum(bkg_sub[args.sig0:args.sig1])
            counts = c if counts is None else c*args.alpha + counts*(1-args.alpha)
            print(datetime.now(), '-', f'cs: {cspec:.1f} counts {counts:.1f}')
        base.stop()
    elif args.command == 'acq':
        nhits = 0
        with open(args.filename, 'wb') as fhits:
            base.set_acq_mode_list()
            base.start()
            t0 = datetime.now()
            while (datetime.now() - t0).total_seconds < args.duration:
                hits = base.hits
                nhits += len(hits)
                if len(hits) > 0: fhits.write(pack(f'{len(hits)}I', *hits))
            base.stop()
        print(f"Collected {nhits} hits")
        print(f"Livetime {base.livetime:.3f} s")
        print(f"Realtime {base.realtime:.3f} s")
