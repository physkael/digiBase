# digiBase
Python interface to ORTEC/AMETEK digital MCA PMT base, the [digiBASE](https://www.ortec-online.com/products/electronic-instruments/photomultiplier-tube-bases/digibase).

The digiBASE plugs into JEDEC B14-38 sockets for 10-dynode-stage, 14-pin photomultiplier tubes.
It provides the high voltage bias (50 - 1200V) and digitizes phototube pulses with a 10-bit
ADC in one of two modes of operation:

* Pulseheight analysis (PHA) mode, where PMT pulses are binned into a 1024 element histogram,
  much like classic multichannel analyzers (MCAs);
* In list mode acquisition PMT pulses are available as an event-by-event list, 
  each with a coarse 1 us timestamp</dd>

This is a 100% Python rewrite of C library interfaces to the digiBASE:

* [libdbaserh](https://github.com/kjbilton/libdbaserh)
* [libdbase](https://github.com/SkyToGround/libdbase)

If you don't want to use the AMETEK Connections library, or can't, you may find this useful. 
I wrote this interface because I needed to create a Raspberry Pi data acquisition system for
use in the field, outside the laboratory environment. The functionality is basic but 
currently supports:

* HV programming
* HV readback (version 0.3+)
* ADC _fine_ gain setting
* Livetime / realtime setting and reading
* Lower-level discriminator set
* EXT gate OFF, ENABLED, COINCIDENCE modes
* PHA mode
* List-mode acquisition

It connects to the digiBASE over the USB bus and supports devices with 
USB vendor ID = 0x0a2d and product ID = 0x000f (digiBASE) or 0x001f (digiBASE-RH), 
which present slightly different communication interfaces.

## Dependencies
Python 3.8+ is required. Additionally, it depends on the following packages:

* pyusb
* NumPy
* pytest (optional, to run unit tests)

## Installation
Digibase is now a Python package on PyPI and is most easily installed using `pip`:
```base
$ pip install digibase
```
which should install the project and all dependencies. 

### DigiBase Firmware
Device firmware must be loaded at power up. ORTEC distributes this firmware with
their MAESTRO and Connection software. You may find this in the distribution media
or in the install directories of the aforementioned software, in `\WINDOWS`, or 
in `\WINDOWS\SYSTEM32` with filename `digiBase.rbf` or `digiBaseRH.rbf`. Place this
file in the current working directory or set the environment variable 
`DBASE_FIRMWARE` to point to the file.

### USB Device Permission (Linux)
Under Linux the module may fail to open the USB device due to lack of permission. 
While it's always possible to `sudo chown 666 /dev/bus/usb/xxx/yyy` it will likely
be reset across power off or even after unplugging and plugging the device back in.
The better solution in this case is to add a custom udev rule:

```bash
sudo echo <<EOF > /etc/udev/rules.d/50-usb-perms.rules
SUBSYSTEM=="usb", ATTRS{idVendor}=="0a2d", GROUP="users", MODE="0666"
EOF
```

## Basic Usage
This project is primarily intended to be used as a library module that can be combined 
with other Python frameworks such as NumPy, SciPy, and matplotlib to realize 
data analysis and visualization pipelines for scintillator-based radiation detectors.
The module may also be invoked from the command line to perform a limited set of
functions: collection of MCA spectra and list-mode PMT hits to a data file and 
background-subtracted gamma detection.

```bash
$ python -m digibase --help
```
will provide help on the various commands and options it supports.

### Python Module

As of version 0.3.1, multiple devices are supported and can be readout simultanesously.
If you don't specify a serial number as argument to instance creation, it will connect 
to the first one found according to the pyusb documentation. This may be 
non deterministic behavior:

```python
from digibase import digiBase, ExtGateMode
from time import sleep
base = digiBase()
print('Opened digiBase, serial number', base.serial)
```

should open the device and provide a serial number. If you provide a serial number as
a string or an integer, it will search for and connect only to the device with that
serial number:

```python
base_a = digiBase(12)
base_b = digiBase(1830)
```

### Configuration
At this point I don't specify the configuration of the device at power-up, and as far as
I can tell the configuration does not persist across power down / power up. Therefore
users __must__ ensure that the device is properly configured the first time it is connected.

#### PMT Bias
High voltage bias for the PMT dynodes is programmed and enabled/disabled in separate steps:

```python
base.hv = 800
base.hv_enabled = True
```

will set the HV to 800 V and turn it on if it is not already on. To turn off the HV,
set the `hv_enabled` property to `False`:
```python
base.hv_enabled = False
```

Electro-optical gain for photomultipliers typically behaves as 
$G = G_0 \left(\frac{V}{V_0}\right)^p$ where $p\sim 5-8$. 
It will depend on what's plugged into the socket.

#### Livetime and Realtime Counters and Presetting Acquisition Time
The digiBASE contains counters to separately track realtime and livetime. 
Furthermore, acquisition can be preset to stop when these counters reach a 
certain value. The following will setup the acquisition to stop either 
after 75 s of wall time or after one minute of livetime, whichever
occurs first:
```python
base.realtime_preset = 75.0
base.livetime_preset = 60.0 
base.set_presets(livetime=True, realtime=True)
```

#### Using the External Gate
Hit collection can be suppressed using a TTL-level signal connected to
the SMA input on the base. This suppression occurs for both PHA _and_
list mode acquisitions. The external gate mode determines how the base
responds to this external gate:

* When `base.ext_gate = ExtGateMode.OFF`, the external gate is ignored, _i.e._ 
  acquisition continues.
* When `base.ext_gate = ExtGateMode.ENABLED`, a TTL low on the external gate
  will suspend the data acquisition. As far as I can tell, this 
  also _stops_ the livetime counter as well as the microsecond
  timestamp counter in list acquisition mode.
* When `base.ext_gate = ExtGateMode.COINCIDENCE`, TTL low will stop hit
  collection (i.e. no hits will fill the MCA channels in PHA
  mode and hits will not appear in list mode), however the livetime
  and timestamp counters continue to tick.

#### Gain
Electronic amplifier gain is set and read by the `fine_gain` property of the
`digiBase` class:
```python
base.fine_gain = 1.0
```
The digiBASE can apparently adjust this parameter internally in order to
track gain and offset drifts, as documented in the device manual, by
tracking a peak in the acquired spectrum. This feature is enabled by
passing triplets of (high_channel, center_channel, low_channel) to
either of the gain or zero named parameters of the `auto_stabilize`
method:
```python
base.auto_stabilize(gain=(80, 75, 70), zero=(80, 75, 70))
```
will turn on both gain and offset stabilization using a peak that 
should be centered at 75 ADC counts inside an ROI of 70 to 80 ADC counts.
_Note_: this feature is not tested; I recommend turning off auto
stabilization which can be effected by calling with arguments 
set to `None`:
```python
base.auto_stabilize(gain=None, zero=None)
```
or just
```python
base.auto_stabilize()
```

### PHA Mode Acquisition
A 15 second run in PHA mode with PMT set to 800 V, the lower-level 
discriminator set to 24 (ADC counts), and suppressing hits that
are not coincident with a TTL high on the external gate signal 
might be configured like this:

```python
base.hv = 800
base.hv_enabled = True
base.lld = 24
base.ext_gate = ExtGateMode.COINCIDENCE
base.livetime_preset = 15.0 
base.set_acq_mode_pha()

sleep(5)        # Sleep 5 seconds to allow HV to stabilize 
base.start()    # Start the acquisition
```

The run should automatically stop after 15 sec of livetime have elapsed.
Note that the device does not block so you can stop the acquisition early,
if desired.

```python
sleep(5)
base.stop()
```

In any case you need to turn off the acquistion before starting again.

To access the pulseheight spectrum / MCA channels:

```python
spectrum = base.spectrum
```

which returns a python list of integers of length 1024.

### List Mode Acquisition
The _list mode_ acquisition is a powerful feature of the digiBASE. Instead of 
having logic on the base fill histogram bins with the ADC values you get the individual 
PMT hits themselves along with microsecond-level timestamps. To invoke list mode 
instead of PHA:

```python
base.set_acq_mode_list()
sleep(5) # If needed - only first time after changing HV
base.start()
```

Now don't dilly-dally before reading out the list buffer - it's only 128k elements 
(or maybe bytes in which case it's only 32k elements!) deep. If the internal 
buffer fills the acquisition stops (instead of acting like a queue and dropping
early hits).

```python
hits = []
while some_condition_is_true:
    while len(new_hits := base.hits) > 0: hits += new_hits
```

The device reads are limited to 4096 bytes so you need
to ensure that there are not hits left in the buffer, 
hence that inner read loop. The hits themselves are 32-bit 
integers which encode time and charge. There are actually 
two kinds of data that are encountered in the hit list readout:

* PMT hits have bit 31 clear. In this case bits 30-21 are 10-bit ADC / charge and
bits 20-0 are time in units of microseconds (according to the not very precise
local oscillator on the digiBase);
* Time rollover words have bit 31 set. In this case bits 30-0 are the time epoch
in microseconds. Because the PMT hits only have 21 bit these rollover markers 
allow for rollover correction.

Here's an example of how to use a hit list populated with PMT hits and rollover
words:

```python
t20 = 0
hit_times = []
hit_q = []
for h in hits:
    if h & 0x8000_0000:
        t20 = h & 0x7fff_ffff
    else:
        t = t20 + (h & 0x001f_ffff)
        hit_times.append(t)
        hit_q.append((h >> 21) & 0x3ff)
```



