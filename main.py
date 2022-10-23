import os
import sys
import glob
import time
import random
import arrow
import requests
from PIL import Image
import win32api, win32con, win32gui
from datetime import *
from screeninfo import get_monitors, Monitor

# API KEY : b03e11fb78b499fc7bd029dc4a90a701

dir = "F:\\Projets\\persona-wallpaper"
os.chdir(dir)

HOUR = datetime.now().hour
DAY = str(datetime.now().day)

def getTotalWidth(widths):
	# Get total width of the image
	total_width = 0

	for width in widths:
		total_width += width
	
	return total_width

def createDayImage(day):
	# Define every numbers of the day date
	numbersList = list(DAY)
	imagesDir = []
	for number in numbersList:
		imagesDir.append(dir + "\\images\\date\\" + number + ".png")

	images = [Image.open(x) for x in imagesDir]
	widths, heights = zip(*(i.size for i in images))
	
	date_image = Image.new('RGBA', (getTotalWidth(widths), heights[0]))

	actualWidth = 0
	for i in range(len(images)):
		date_image.paste(images[i], (actualWidth, 0))
		actualWidth += widths[i]

	return date_image



createDayImage(DAY).show()





# response = requests.get(
# 	'https://api.stormglass.io/v2/weather/point',
# 	params={
# 		'lat': 43.497,
# 		'lng': 5.12,
# 		'params': ','.join(['airTemperature']),
# 		'start': now,  # Convert to UTC timestamp
# 		'end': now  # Convert to UTC timestamp
# 	},
# 	headers={
# 		'Authorization': '1fce8498-5218-11ed-92e6-0242ac130002-1fce84f2-5218-11ed-92e6-0242ac130002'
# 	}
# )
#print(response.content)

# Function to actually set the wallpaper as tiled image
# > We will set background as a single image (which is 2 images merged)
def setWallpaper(path):
    key = win32api.RegOpenKeyEx(win32con.HKEY_CURRENT_USER,"Control Panel\\Desktop",0,win32con.KEY_SET_VALUE)
    win32api.RegSetValueEx(key, "WallpaperStyle", 0, win32con.REG_SZ, "0")
    win32api.RegSetValueEx(key, "TileWallpaper", 0, win32con.REG_SZ, "1")
    win32gui.SystemParametersInfo(win32con.SPI_SETDESKWALLPAPER, path, 1+2)

# ================================================================ #
