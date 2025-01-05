from spidev import SpiDev
from gpiozero import DigitalOutputDevice
from time import sleep
import sys
import re
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument('--graph', action='store_true')
parser.add_argument('--save-frames')
parser.add_argument('--delay', type=float, default=1.0)

args = parser.parse_args()

spi = SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 4_000_000
spi.mode = 0b11

dc = DigitalOutputDevice('GPIO19')
reset = DigitalOutputDevice('GPIO21')
vcc_en = DigitalOutputDevice('GPIO20')
pmoden = DigitalOutputDevice('GPIO18')

dc.off()
reset.on()
vcc_en.off()
pmoden.on()
sleep(0.025)
reset.off()
sleep(0.01)
reset.on()

# SSD1331 initialization
spi.writebytes(bytes((0xfd, 0x12)))  # Unlock
spi.writebytes(bytes((0xae,)))       # Display off
spi.writebytes(bytes((0xa0, 0x72)))  # Set remap
spi.writebytes(bytes((0xa1, 0x00)))  # Set display start line
spi.writebytes(bytes((0xa2, 0x00)))  # Set display offset
spi.writebytes(bytes((0xa4,)))       # Normal display
spi.writebytes(bytes((0xa8, 0x3f)))  # Set multiplex ratio
spi.writebytes(bytes((0xad, 0x8e)))  # Set master configuration
spi.writebytes(bytes((0xb0, 0x0b)))  # Power save mode
spi.writebytes(bytes((0xb1, 0x31)))  # Phase 1 and 2 period adjustment
spi.writebytes(bytes((0xb3, 0xf0)))  # Set display clock divide ratio/oscillator frequency
spi.writebytes(bytes((0x8a, 0x64)))  # Set pre-charge level
spi.writebytes(bytes((0x8b, 0x78)))  # Set pre-charge level
spi.writebytes(bytes((0x8c, 0x64)))  # Set pre-charge level
spi.writebytes(bytes((0xbb, 0x3a)))  # Set pre-charge level
spi.writebytes(bytes((0xbe, 0x3e)))  # Set VCOMH
spi.writebytes(bytes((0x87, 0x06)))  # Set second pre-charge period
spi.writebytes(bytes((0x81, 0xff)))  # Set contrast - color A
spi.writebytes(bytes((0x82, 0xff)))  # Set contrast - color B
spi.writebytes(bytes((0x83, 0xff)))  # Set contrast - color C
spi.writebytes(bytes((0x2e,)))       # Deactivate scroll
spi.writebytes(bytes((0x25, 0x00, 0x00, 0x5f, 0x3f)))  # Clear + set dims

vcc_en.on()
sleep(0.025)
spi.writebytes(bytes((0xaf,)))  # Display on

parse = re.compile(r'.+counts (.+)')
#clockFont = ImageFont.truetype('Mojang-Regular', 8)
clockFont = ImageFont.truetype('visitor1', 10)
signalFont = ImageFont.truetype('Mojang-Bold', 8)

if args.graph:
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    mpl.rcParams['font.family'] = 'sans-serif'
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(7,4))
    ax  = fig.add_subplot()
    ax.grid(True, color='green', linestyle='dashed', linewidth=0.75)
    ax.axhline(0, color='white', linestyle='solid', linewidth=0.5)
    plt.ion()
    t, cts = [], []
    line_plot, = ax.plot(t, cts, 'y')
    ax.set_xlabel('Time')
    ax.set_ylabel('Excess Counts per Second')
    detect = ax.text(0.5, 0.85, 'Nitrogen Detection', 
                     transform=ax.transAxes, 
                     ha='center', 
                     color='red', 
                     fontsize=24,
                     fontweight=600)
    detect.set_visible(False)

for iframe, line in enumerate(sys.stdin):
    datetime = line[0:24]
    m = parse.match(line[24:])
    c = float(m.group(1)) if m else 0.0
    
    if datetime[0:4] == 'User': break

    if args.graph:
        t.append(np.datetime64(datetime, 'ms'))
        cts.append(c)

        if len(t) > 100:
            t.pop(0)
            cts.pop(0)

        line_plot.set_xdata(t)
        line_plot.set_ydata(cts)

        t1 = t[-1]
        t0 = t1 - np.timedelta64(100, 's')
        
        ax.set_xlim((t0, t1))
        ax.set_ylim((-1.25, 1.25))
        detect.set_visible(c >= 0.35)
        if args.save_frames is not None:
            filename = args.save_frames + f'-{iframe:04d}.png'
            plt.savefig(filename, dpi=300)
        plt.draw()
        
    # Create image /w/ PIL and write to GDDRAM
    img = Image.new('RGB', (96, 64), color='black')
    draw = ImageDraw.Draw(img)
    timestring = datetime[:10].replace('-', '') + ' ' + datetime[11:19]
    draw.text((2, 2), timestring, font=clockFont, fill='white', anchor='la')
    draw.text((2, 16), f'CTS: {c:+.1f}', font=signalFont, fill='white', anchor='la')
    rlen = (c + 1) * 15
    rlen = max(rlen, 0)
    rlen = min(rlen, 30)
    if c < 0.1: 
        fill_color = 'green'
    elif c < 0.35:
        fill_color = 'yellow'
    else:
        fill_color = 'red'
    
    draw.rectangle(((64, 16), (64 + rlen, 24)), fill=fill_color)

    if c >= 0.3:
        draw.text((48, 35), 'N DETECTION!', font=signalFont, fill='red', anchor='ma')

    # Green bars to left for < 0
    img.save('fb.png')

    m24 = np.array(img).astype(np.uint16)
    m16 = (m24[...,0] & 0b11111000) | \
          (m24[...,1] >> 5) | \
          ((m24[...,1] & 0b111) << 13) | \
          ((m24[...,2] & 0b11111000) << 5)
    
    dc.on()
    spi.writebytes2(m16.view(np.uint8).flatten())

    if args.graph:
        plt.pause(args.delay)
    else:
        sleep(args.delay)

if args.graph:
    plt.ioff()
    # plt.show()
