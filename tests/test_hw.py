# (C) 2025 Kael Hanson (kael.hanson@gmail.com)

# Tests that require an actual hardware device to be connected

import pytest
import digibase
from random import randint, uniform
from time import sleep

@pytest.fixture(scope='module')
def base_dev():
    try:
        base = digibase.digiBase()
        yield base
        del base
    except ValueError:
        pytest.skip('No device connected')

def test_serial_read(base_dev):
    assert len(base_dev.serial) > 0
    del base_dev

def test_set_hv(base_dev):
    base_dev.hv_enabled = False
    for i in range(10):
        hvset = randint(50, 1200)
        base_dev.hv = hvset
        # HV is quantized in 1.25 V steps
        assert abs(base_dev.hv - hvset < 1)
    base_dev.hv = 800

def test_set_fine_gain(base_dev):
    for i in range(10):
        fine_gain = uniform(0.25, 2.0)
        base_dev.fine_gain = fine_gain
        assert abs(base_dev.fine_gain - fine_gain) < 0.001
    base_dev.fine_gain = 0.5

def test_set_ext_gate(base_dev):
    base_dev.ext_gate = digibase.ExtGateMode.ENABLED
    assert base_dev.ext_gate == digibase.ExtGateMode.ENABLED
    base_dev.ext_gate = digibase.ExtGateMode.COINCIDENCE
    assert base_dev.ext_gate == digibase.ExtGateMode.COINCIDENCE
    base_dev.ext_gate = digibase.ExtGateMode.OFF
    assert base_dev.ext_gate == digibase.ExtGateMode.OFF

def test_set_lld(base_dev):
    for i in range(10):
        lld = randint(0, 1000)
        base_dev.lld = lld
        assert base_dev.lld == lld

def test_realtime_preset(base_dev):
    base_dev.stop()
    base_dev.ext_gate = digibase.ExtGateMode.OFF
    base_dev.realtime_preset = 1.0
    assert base_dev.realtime_preset == 1.0
    base_dev.clear_counters()
    base_dev.set_presets(livetime=False, realtime=True)
    base_dev.start()
    sleep(1.25)
    base_dev.stop()
    assert base_dev.realtime > 0.99 and base_dev.realtime < 1.01
    base_dev.set_presets()