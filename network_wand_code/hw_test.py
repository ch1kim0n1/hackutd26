#!/usr/bin/env python3
"""Check each wand part on its own. Run: sudo .venv/bin/python hw_test.py"""
import time
import yaml

CFG = yaml.safe_load(open("config.yaml"))

print("1/4 OLED ...")
try:
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import ssd1306
    oled = ssd1306(i2c(port=CFG["oled"]["i2c_port"], address=CFG["oled"]["address"]))
    with canvas(oled) as d:
        d.rectangle(oled.bounding_box, outline="white")
        d.text((10, 20), "NETWORK WAND", fill="white")
        d.text((10, 36), "OLED OK", fill="white")
    print("   OK - check the screen")
except Exception as e:
    print("   FAIL:", e, "-> run 'i2cdetect -y 1', expect 3c")

print("2/4 LEDs ...")
try:
    import board
    import neopixel_spi
    px = neopixel_spi.NeoPixel_SPI(board.SPI(), CFG["leds"]["count"], brightness=0.3,
                                   pixel_order=neopixel_spi.GRB, auto_write=False)
    for c in [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 220, 255), (0, 0, 0)]:
        px.fill(c); px.show(); time.sleep(0.5)
    print("   OK - you should have seen red, green, blue, cyan")
except Exception as e:
    print("   FAIL:", e, "-> is SPI enabled? (raspi-config)")

print("3/4 Buzzer ...")
try:
    from gpiozero import Buzzer
    bz = Buzzer(CFG["pins"]["buzzer"])
    for _ in range(3):
        bz.on(); time.sleep(0.1); bz.off(); time.sleep(0.15)
    print("   OK - three beeps")
except Exception as e:
    print("   FAIL:", e)

print("4/4 Buttons: press each button (15 s) ...")
try:
    from gpiozero import Button
    b1 = Button(CFG["pins"]["button1"], pull_up=True, bounce_time=0.03)
    b2 = Button(CFG["pins"]["button2"], pull_up=True, bounce_time=0.03)
    b1.when_pressed = lambda: print("   button 1 pressed")
    b2.when_pressed = lambda: print("   button 2 pressed")
    time.sleep(15)
except Exception as e:
    print("   FAIL:", e)
print("done")
