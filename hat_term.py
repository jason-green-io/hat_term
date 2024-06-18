#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import shlex
import pyte
import ptyprocess
import threading
import time
from PIL import Image, ImageDraw
from bdflib import reader
import json
import logging
import os 
import sys
import random
import subprocess
import displayhatmini
import shutil

tmux = "tmux"
tmuxSession = "hat_term"

dir_path = os.path.dirname(os.path.realpath(__file__))

#setup logging
logging.basicConfig(level=logging.DEBUG)

# open theme file
with open(os.path.join(dir_path, "theme.json"), "r") as handle:
    logging.info("Loading color theme")
    theme = json.load(handle)

# load miniwi
with open(os.path.join(dir_path, "miniwi-qrunicode.bdf"), "rb") as handle:
    logging.info("Reading font file")
    bdffont = reader.read_bdf(handle)


def getGlyph(number, font):
    """extract a glyph from the BDF font"""
    glyph = font[number]
    glyphPixels = glyph.iter_pixels()

    img = Image.new('1', (4, 9))
    pixels = img.load()
 
    for y, Y in enumerate(glyphPixels):
        for x, X in enumerate(Y):
            pixels[x, y] = X

    return img

# this holds all the glyphs as images
logging.info("Loading glyphs from font")
glyphDict = {cp: getGlyph(cp, bdffont) for cp in bdffont.codepoints()}

# get the display size
width = displayhatmini.DisplayHATMini.WIDTH
height = displayhatmini.DisplayHATMini.HEIGHT

# set the orientation


# sleep between reads on the buffer
sleep = 0.1

# font attributes
fontwidth = 4
fontheight = 8

# calculate the rows and columns based on the font and display width
columns = int(width / fontwidth)
rows = int(height / fontheight)

# create the terminal emulator 
screen = pyte.Screen(columns, rows)
stream = pyte.ByteStream(screen)

# run a tmux and create/reattach to the "hat_term" session
argv = shlex.split(f"bash -c 'TERM=hat_term {tmux} -2 new-session -A -s {tmuxSession}'")


def writer():
    """read from the process in a pseudo termnial and write it to the terminal emulator"""
    p = ptyprocess.PtyProcess.spawn(argv, dimensions=(rows, columns))

    while True:
        try:
            data = p.read(4096)
        except:
            logging.info("Something went wrong with reading the pty")
            sys.exit(1)
        if not data:
            pass
        else:
            stream.feed(data)

# start tmux and write to the terminal emulator
writerThread = threading.Thread(target=writer, name="glue")
writerThread.daemon = True
writerThread.start()
logging.info("Started writer")

# create the image for the display
row_image = Image.new("RGB", (width, fontheight), "black")
image = Image.new("RGB", (width, height), "black")
# get a draw object to paste the font glyphs and stuff
draw = ImageDraw.Draw(row_image)

display = displayhatmini.DisplayHATMini(image) 

def button_callback(pin):
    key = {
        display.BUTTON_A: 'a',
        display.BUTTON_B: 'b',
        display.BUTTON_X: 'x',
        display.BUTTON_Y: 'y'
    }[pin]
    if display.read_button(pin):
        if key == 'a':
            subprocess.Popen([tmux, "next-window", "-t", tmuxSession],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        elif key == 'b':
            subprocess.Popen([tmux, "previous-window", "-t", tmuxSession],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        elif key =="x":
            subprocess.Popen([tmux, "send-keys", "up"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        elif key =="y":
            subprocess.Popen([tmux, "send-keys", "down"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    logging.info("%s, %s", pin, display.read_button(pin))

display.on_button_pressed(button_callback)


# create the old cursor
oldcursor = (0, 0, None)

logging.info("Starting screen")

while writerThread.is_alive():
    
    # get the current cursor
    cursor = (int(screen.cursor.x), int(screen.cursor.y), ord(screen.cursor.attrs.data))

    # do something only if content has changed or cursor was moved
    if (screen.dirty or oldcursor != cursor):

        # get the rows that changed, an clean the dirty
        dirtyrows = screen.dirty.copy()
        screen.dirty.clear()

        # add the cursor rows so they also get redrawn
        dirtyrows.add(cursor[1])
        dirtyrows.add(oldcursor[1])

        logging.debug("screen: dirty %s", dirtyrows)
        
        # iterate through all the changed characters
        for row in dirtyrows:
            for col in range(columns):
                char = screen.buffer[row][col]
                # check for bold attribute
                if char.bold:
                    fgfill = theme.get(char.fg, "#" + char.fg) if char.fg != "default" else theme["foreground"]
                else:
                    fgfill = theme.get(char.fg, "#" + char.fg) if char.fg != "default" else theme["foreground"]
                
                # set the background
                bgfill = theme.get(char.bg, "#" + char.bg) if char.bg != "default" else theme["background"]
                
                # check for reverse attribute
                if char.reverse:
                    fgfill, bgfill  = bgfill, fgfill
                
                # draw the background
                draw.rectangle([(col * fontwidth, 0),(col * fontwidth + fontwidth - 1, fontheight - 1)], outline=bgfill, fill=bgfill)
                
                # draw the character glyph, return "?" if the font doesn't have it
                draw.bitmap((col * fontwidth, 0), glyphDict.get(ord(char.data if len(char.data) == 1 else "?"), glyphDict[63]), fill=fgfill)
                
                # check for underscore
                if char.underscore:
                    draw.line([(col * fontwidth, fontheight -1 ), (col * fontwidth + fontwidth - 1, fontheight - 1)], fill=fgfill)
                
                # draw the cursor if it's on this row 
                if cursor[1] == row:
                    cur_x, cur_y = cursor[0], cursor[1]
                    start_x = cur_x * fontwidth
                    start_y = fontheight - 1
                    draw.line((start_x, start_y, start_x + fontwidth, start_y), fill="white")        
            
            # draw the row on the screen
            image.paste(row_image, (0, row * 8))
        display.display()
        # save the cursor
        oldcursor = cursor
        
        # write image to file
        image.save("hat_term.png")
        
        #rotated = row_image.transpose(Image.ROTATE_90)
    else:

        # sleep a bit before chercking for updates
        time.sleep(sleep)
