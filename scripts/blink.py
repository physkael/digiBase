from spidev import SpiDev
from gpiozero import DigitalOutputDevice
from time import sleep
from datetime import datetime, timedelta
import sys
import re
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from argparse import ArgumentParser

def filegen(f):
    input_parse = re.compile(r'.+counts (.+)')
    for line in f:
        if line[0:4] == 'User': return
        datetime = np.datetime64(line[0:24], 'ms')
        m = input_parse.match(line[24:])
        c = float(m.group(1)) if m else 0.0
        yield datetime, c

def rvgen(mu, bkg, alpha=1.0, dt=np.timedelta64(1, 's'), t0=np.datetime64('now', 'ms')):
    t = t0
    c_ema = 0.
    for c in np.random.poisson(mu) - bkg:
        c_ema = alpha * c + (1.0 - alpha) * c_ema
        yield t, c_ema
        t += dt

parser = ArgumentParser()
parser.add_argument('-T', '--threshold', type=float, default=0.33, 
                    help='Sets the N detection message threshold')
parser.add_argument('-t', '--tft', action='store_true',
                    help='Output to TFT')
parser.add_argument('-g', '--graph', action='store_true',
                    help='Matplotlib graph output')
parser.add_argument('-n', '--n-pts', type=int, default=100)
parser.add_argument('--y-min', type=float, default=0,
                    help='MPL Graph (if enabled) Minimum Y')
parser.add_argument('--y-max', type=float, default=0,
                    help='MPL Graph (if enabled) Maximum Y')
parser.add_argument('-f', '--save-frames')
parser.add_argument('-r', '--random', type=float, nargs=3, default=None)
parser.add_argument('-a', '--alpha', type=float, default=1.0)
parser.add_argument('-d', '--delay', type=float, default=1.0)

args = parser.parse_args()

if args.tft:
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
    if args.y_max > args.y_min: 
        ax.set_ylim((args.y_min, args.y_max))
    else:
        ax.autoscale(True, axis='y')

    detect = ax.text(0.5, 0.85, 'Nitrogen Detection', 
                     transform=ax.transAxes, 
                     ha='center', 
                     color='red', 
                     fontsize=24,
                     fontweight=600)
    detect.set_visible(False)

# coupla options for input
# (1) stdin - output from python -m digibase detect 
# (2) random simulation with options (sequence repeats for 600 periods)
#     (a) mu = 5, bkg = 4, only bkg for 30 per, then mu for 30 per
#     (b) mu = 5, bkg = 4, bkg for 50 per, mu for 10 per
#     (c) mu = 8, bkg = 4, bkg for 50 per, mu for 10 per

if args.random is None:
    src = filegen(sys.stdin)
else:
    sig, bkg, duty = args.random
    n_on  = int(duty * 60)
    n_off = 60 - n_on
    mu = np.array(([[bkg] * n_off + [bkg+sig] * n_on] * 10), 'd').flatten()
    #print(mu)
    src = rvgen(mu, bkg, alpha=args.alpha)

for iframe, (ts, c) in enumerate(src):

    if args.graph:
        t.append(ts)
        cts.append(c)

        if len(t) > args.n_pts:
            t.pop(0)
            cts.pop(0)

        cnda = np.array(cts)
        if args.y_max > args.y_min:
            y0 = args.y_min
            y1 = args.y_max
        else:
            y0 = np.min(cnda)
            y1 = np.max(cnda)

        line_plot.set_xdata(t)
        line_plot.set_ydata(cts)

        t1 = t[-1]
        t0 = t1 - np.timedelta64(args.n_pts, 's')
        
        ax.set_xlim((t0, t1))
        ax.set_ylim((y0, y1))

        #ax.yaxis.set_major_locator(mpl.ticker.MaxNLocator(nbins='auto'))
        ax.xaxis.set_major_formatter(mpl.dates.DateFormatter('%H:%M:%S'))

        detect.set_visible(c >= args.threshold)
        if args.save_frames is not None:
            filename = args.save_frames + f'-{iframe:04d}.png'
            plt.savefig(filename, dpi=300)
        plt.draw()
        
    if args.tft:
        # Create image /w/ PIL and write to GDDRAM
        img = Image.new('RGB', (96, 64), color='black')
        draw = ImageDraw.Draw(img)
        timestring = ts.astype(datetime).strftime('%m/%d %H:%M:%S')
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

        if c >= args.threshold:
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

