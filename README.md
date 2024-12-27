# digiBase
Python interface to ORTEC/AMETEK digital MCA PMT base.

This is a 100% Python rewrite of C library interfaces:

* [libdbaserh](https://github.com/kjbilton/libdbaserh)
* [libdbase](https://github.com/SkyToGround/libdbase)

If you don't want to use the AMETEK Connections library, or can't, you may find this useful. 
I wrote this interface because I needed to create a Raspberry Pi data acquisition system for
use in remote locations. The functionality is basic but currently supports:

* HV set
* Livetime / realtime set
* Lower-level discriminator set
* EXT gate OFF, ENABLED, COINCIDENCE modes
* PHA mode
* List-mode acquisition

This connects to ORTEC/AMETEK digiBases over the USB bus and supports devices with USB vendor ID = 0x0a2d and product ID = 0x000f or 0x001f, which present slightly different communication
interfaces.

## Dependencies

* pyusb
* NumPy (I will try to refactor this out)

## Installation
I am actively hacking on this right now so it's just a python file. Download, set PYTHONPATH if necessary, and voila!

## Basic Usage

This currently (I think) only supports one device so if you have multiple devices connected I think it will find the first one. ORTEC seems to have manufactured several versions 

```python
from digibase import digiBase, ExtGateMode
from time import sleep
base = digiBase()
print('Opened digiBase, serial number', base.serial)
```

should open the device and provide a serial number. 

### PHA Mode Acquisition
To setup a run in PHA mode you would need to configure settings:

```python
base.hv = 800
base.enable_hv()
base.lld = 24
base.ext_gate(ExtGateMode.COINCIDENCE)
base.realtime_preset = 15.0 # to set for 15 seconds
base.livetime_preset = 15.0 
base.set_acq_mode_pha()

sleep(5)        # Sleep 5 seconds to allow HV to stabilize 
base.start()    # Start the acquisition
```

The run should automatically stop after 15 sec since you programmed a preset above.
Note that the device does not block so you can stop the acquisition early if desired.

```python
sleep(5)
base.stop()
```

In any case you need to turn off the acquistion before starting again.

To access the pulseheight spectrum / MCA channels:

```python
spectrum = base.spectrum
```

which returns a python `array.array` type. It will be 1024, 32-bit unsigned integers.

### List Mode Acquisition
I find the so-called _list mode_ acquisition quite powerful. Instead of having logic on
the base fill histogram bins with the ADC values you get the individual PMT hits themselves
along with microsecond-level timestamps. To invoke list mode instead of PHA:

```python
base.set_acq_mode_list()
sleep(5) # If needed - only first time after changing HV
base.start()
```

Now don't dilly-dally before reading out the list buffer - it's only 128k elements 
(or maybe bytes in which case it's only 32k elements!) deep. The base can run 
sustained over 32 ksps so you have about a second to start draining the buffer:

```python
hits = []
while some_condition_is_true:
    while new_hits := base.hits > 0: hits += new_hits
```

I've used the Python 3.8+ walrus operator to enter a tight loop that drains the
device's internal buffer. The device reads are limited to 4096 bytes so you need
to ensure that there are not hits left in the buffer, hence that inner read loop.

The hits themselves are 32-bit integers which encode time and charge. There are
actually two kinds of data that are encountered in the hit list readout:

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

