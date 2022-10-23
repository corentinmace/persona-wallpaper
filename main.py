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

dir = "C:\\persona-wallpaper"
os.chdir(dir)

HOUR = datetime.now().hour
DAY = str(datetime.now().day)
MONTH = str(datetime.now().month)


def getDayOrNight(hour):
	# Returns day or night depending on the hour
	if hour >= 7 and hour < 19:
		return "day"
	else:
		return "night"


def getMaxHeight(heights):
	# Return max height of the image
	maxHeight = 0
	for height in heights:
		if height > maxHeight:
			maxHeight = height

	return maxHeight


def getTotalWidth(widths):
	# Return total width of the image
	total_width = 0

	for width in widths:
		total_width += width
	
	return total_width


def getDayOfTheWeek():
	# Returns the day of the week (mon, tue, wed, thu, fri, sat, sun)
	return datetime.now().strftime("%a").lower()


def getMonth():
	return datetime.now().strftime("%b").lower()


def getMeteoFromApi():
	# Returns the meteo from the api
	response = requests.get('https://api.openweathermap.org/data/2.5/weather?lat=43.474663&lon=5.167665&appid=b03e11fb78b499fc7bd029dc4a90a701')
	jsonData = response.json()
	meteoDescription = jsonData['weather'][0]['description']

	if(meteoDescription == 'few clouds') or (meteoDescription == 'scattered clouds') or (meteoDescription == 'broken clouds'):
		return 'cloud'
	elif(meteoDescription == 'shower rain') or (meteoDescription == 'rain') or (meteoDescription == 'thunderstorm') or (meteoDescription == 'mist'):
		return 'rain'
	elif(meteoDescription == 'snow'):
		return 'snow'
	else:
		return 'sun'


def createDateImage(day):
	# Define every numbers of the day date
	numbersList = list(day)
	imagesDir = []
	for number in numbersList:
		imagesDir.append(dir + "\\images\\date\\" + number + ".png")

	images = [Image.open(x) for x in imagesDir]
	widths, heights = zip(*(i.size for i in images))

	date_image = Image.new('RGBA', (getTotalWidth(widths), getMaxHeight(heights)))

	actualWidth = 0
	for i in range(len(images)):
		date_image.paste(images[i], (actualWidth, 0))
		actualWidth += widths[i] - 10

	return date_image


def getDayImage():
	# Return the day image depending on the day or the night (monday, tuesday, wednesday, thursday, friday, saturday, sunday)
	dayImage = dir + "\\images\\days\\" + getDayOrNight(HOUR) + "\\" + getDayOfTheWeek() + ".png"
	return Image.open(dayImage)


def getMonthImage():
	# Return the month image depending on the month (january, february, march, april, may, june, july, august, september, october, november, december)
	monthImage = dir + "\\images\\months\\" + getMonth() + ".png"
	return Image.open(monthImage)


def getMeteoImage():
	# Return the meteo image depending on the meteo (sun, rain, snow, cloud)
	meteoImage = dir + "\\images\\meteo\\" + getMeteoFromApi() + ".png"
	return Image.open(meteoImage)


def getBackground():
	# Return the background image depending on the day or the night
	backgroundImage = dir + "\\images\\background\\" + getDayOrNight(HOUR) + ".png"
	return Image.open(backgroundImage)


def createWallpaper():
	background = getBackground()
	background.convert('RGBA')
	day = getDayImage()
	date = createDateImage(DAY)
	month = getMonthImage()
	meteo = getMeteoImage()

	background.paste(month, (30, 30), month)
	background.paste(meteo, (230, 30), meteo)
	background.paste(date, (110, 25), date)
	background.paste(day, (110, 100), day)

	background.save("final.png", quality=100, subsampling=0)


# Function to actually set the wallpaper as tiled image
# > We will set background as a single image (which is 2 images merged)
def setWallpaper(path):
    key = win32api.RegOpenKeyEx(win32con.HKEY_CURRENT_USER,"Control Panel\\Desktop",0,win32con.KEY_SET_VALUE)
    win32api.RegSetValueEx(key, "WallpaperStyle", 0, win32con.REG_SZ, "0")
    win32api.RegSetValueEx(key, "TileWallpaper", 0, win32con.REG_SZ, "1")
    win32gui.SystemParametersInfo(win32con.SPI_SETDESKWALLPAPER, path, 1+2)

# ================================================================ #


createWallpaper()
setWallpaper(dir + "\\final.png")
