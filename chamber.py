#
# Copyright (c) 2019 Michael Schmidt
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import threading
import datetime
import time
import logging
import controller
import tilt
from setup_logger import logger
import configparser

logger = logging.getLogger('CHAMBER')
logger.setLevel(logging.INFO)

UPDATE_INVERVAL = 1 # update interval in seconds
CONFIGFILE = "chamber.ini"

DEFAULT_TEMP = -999
DEFAULT_SG = -999
DEFAULT_BUFFER_BEER_TEMP = 0.5       # +/- degrees celcius beer is from target when heating/cooling will be turned on
DEFAULT_BUFFER_CHAMBER_SCALE = 5.0   # scale factor of temperature delta chamber is from target controlling when heating/cooling will be turned on/off


class Chamber(threading.Thread):

    def __init__(self, _tilt):
        threading.Thread.__init__(self)
        self.stopThread = True              # flag used for stopping the background thread
        self.control = controller.Controller()
        self.tilt = _tilt
        self.tempDates = [datetime.datetime.now()]
        self.targetTemps = [DEFAULT_TEMP]
        self.targetTemp = DEFAULT_TEMP
        self.bufferBeerTemp = DEFAULT_BUFFER_BEER_TEMP
        self.bufferChamberScale = DEFAULT_BUFFER_CHAMBER_SCALE
        self.beerTemp = DEFAULT_TEMP
        self.beerWireTemp = DEFAULT_TEMP
        self.chamberTemp = DEFAULT_TEMP
        self.beerSG = DEFAULT_SG
        self.timeData = datetime.datetime.now()

        self.control.start()


    # Starts the background thread
    def run(self):
        logger.info("Starting Chamber")
        self.stopThread = False
        
        while self.stopThread != True:
            self._readConf()
            self._evaluate()
            time.sleep(UPDATE_INVERVAL)

        logger.info("Chamber Stopped")


    def __del__(self):
        logger.debug("Delete chamber class")

    def stop(self):
        self.stopThread = True
    
    def _evaluate(self):
        self.control
        self.targetTemps
        self.tempDates
        self.bufferBeerTemp
        self.bufferChamberScale

        # use wired data initially
        if self.control.isDataValid():
            self.beerTemp = self.control.getBeerTemp()
            self.timeData = self.control.timeOfData()
            self.beerWireTemp = self.control.getBeerTemp()
            self.chamberTemp = self.control.getChamberTemp()

        # if Tilt is configured and available replace related values
        if (self.tilt is not None and self.tilt.isDataValid()):
            self.beerTemp = self.tilt.getTemp()
            self.beerSG = self.tilt.getGravity()
            self.timeData = self.tilt.timeOfData()
        
        # beer temp has not been read yet so cannot properly control chamber
        if self.beerTemp == DEFAULT_TEMP:
            return

        _curTime = datetime.datetime.now()
            
        # check which of the temperature change dates have passed
        datesPassed = 0
        for dt in self.tempDates:
            if dt < _curTime:
                datesPassed = datesPassed + 1
        
        # No configured dates have passed, leave chamer powered off
        if datesPassed == 0:
            # Turn off heating and cooling
            logger.debug("Leaving chamber heating/cooling off until first date reached: " + self.tempDates[datesPassed].strftime("%d.%m.%Y %H:%M:%S"))
            self.control.stopHeatingCooling()
            return

        # check if last date has been reached. If so, heating/cooling should stop
        elif datesPassed == len(self.tempDates):
            logger.debug("Last date reached turning heating/cooling off: " + self.tempDates[datesPassed-1].strftime("%d.%m.%Y %H:%M:%S"))
            self.control.stopHeatingCooling()
            return

        # date is within configured range    
        else:
            self.targetTemp = self.targetTemps[datesPassed-1]

            # beer is warmer than target + buffer, consider cooling
            if self.beerTemp > (self.targetTemp + self.bufferBeerTemp):
                # check how much cooler chamber is compared to target, do not want it too low or beer temperature will overshoot too far.
                if (self.targetTemp - self.chamberTemp) < self.bufferChamberScale*(self.beerTemp - self.targetTemp):
                    # Turn cooling ON
                    logger.debug("Cooling to be turned ON - Target: " + str(self.targetTemp) + "; Beer: " + str(self.beerTemp) + "; Chamber: " + str(self.chamberTemp) + "; Beer Buffer: " + str(self.bufferBeerTemp) + "; Chamber Scale: " + str(self.bufferChamberScale))
                    self.control.startCooling()
                else:
                    logger.debug("Chamber is cold enough to cool beer")
                    self.control.stopHeatingCooling()

            # beer is cooler than target + buffer, consider heating
            elif self.beerTemp < (self.targetTemp - self.bufferBeerTemp):
                # check how much hotter chamber is compared to target, do not want it too high or beer temperature will overshoot too far.
               if (self.chamberTemp - self.targetTemp) < self.bufferChamberScale*(self.targetTemp - self.beerTemp):
                    # Turn heating ON
                    logger.debug("Heating to be turned ON - Target: " + str(self.targetTemp) + "; Beer: " + str(self.beerTemp) + "; Chamber: " + str(self.chamberTemp) + "; Beer Buffer: " + str(self.bufferBeerTemp) + "; Chamber Scale: " + str(self.bufferChamberScale))
                    self.control.startHeating()
               else:
                    logger.debug("Chamber is warm enough to heat beer")
                    self.control.stopHeatingCooling()

            # beer is within range of target +/- buffer
            else:
                logger.debug("No heating/cooling needed - Target: " + str(self.targetTemp) + "; Beer: " + str(self.beerTemp) + "; Chamber: " + str(self.chamberTemp) + "; Beer Buffer: " + str(self.bufferBeerTemp) + "; Chamber Scale: " + str(self.bufferChamberScale))
                self.control.stopHeatingCooling()
        return  


    def getTargetTemp(self):
        if self.targetTemp == DEFAULT_TEMP:
            return None
        else:
            return self.targetTemp

    def getBeerTemp(self):
        if self.beerTemp == DEFAULT_TEMP:
            return None
        else:
            return self.beerTemp
    
    def getBeerSG(self):
        if self.beerSG == DEFAULT_SG:
            return None
        else:
            return self.beerSG

    def getWireBeerTemp(self):
        if self.beerWireTemp == DEFAULT_TEMP:
            return None
        else:
            return self.beerWireTemp

    def getChamberTemp(self):
        if self.chamberTemp == DEFAULT_TEMP:
            return None
        else:
            return self.chamberTemp

    # returns time when data was updated
    def timeOfData(self):
        return self.timeData

    # Read class parameters from configuration ini file.
    # Format:
    # [Chamber]
    # MessageLevel = INFO
    # Temps = 18,21,0
    # Dates = 26/03/2019 12:00:00,28/09/2019 13:00:00,14/10/2019 14:00:00,20/04/2020 14:00:00
    # BeerTemperatureBuffer = 0.2
    # ChamberScaleBuffer = 5.0
    
    def _readConf(self):

        try:
            if os.path.isfile(CONFIGFILE) == False:
                logger.error("Chamber configuration file is not valid: "+CONFIGFILE)

            ini = configparser.ConfigParser()
            ini.read(CONFIGFILE)

            if 'Chamber' in ini:
                logger.debug("Reading Chamber config")
        
                config = ini['Chamber']
                
                try:
                    if config["MessageLevel"] == "DEBUG":
                        logger.setLevel(logging.DEBUG)
                    elif config["MessageLevel"] == "WARNING":
                        logger.setLevel(logging.WARNING)
                    elif config["MessageLevel"] == "ERROR":
                        logger.setLevel(logging.ERROR)
                    elif config["MessageLevel"] == "INFO":
                        logger.setLevel(logging.INFO)
                    else:
                        logger.setLevel(logging.INFO)
                except KeyError:
                    logger.setLevel(logging.INFO)
                                    
                # Read temperatures to target for each date
                try:
                    if config["Temps"] != "":
                        self.targetTemps = []
                        t = config["Temps"].split(",")
                        for x in t:
                            self.targetTemps.append(float(x))
                    else:
                        raise Exception
                except:
                    self.targetTemps = [DEFAULT_TEMP]
                    logger.warning("Invalid temp values; using default: "+str(self.targetTemps[0]))

                # Read dates when temperature should change
                try:
                    if config["Dates"] != "":
                        self.tempDates = []
                        dts = config["Dates"].split(",")
                        for x in dts:
                            self.tempDates.append(datetime.datetime.strptime(x, '%d/%m/%Y %H:%M:%S'))
                    else:
                        raise Exception
                except:
                    self.tempDates = [datetime.datetime.now(),datetime.datetime.now()]
                    logger.warning("Invalid date values; using default. Heating/cooling will NOT start")

        
                if len(self.tempDates) != len(self.targetTemps)+1:
                    self.tempDates = [datetime.datetime.now(),datetime.datetime.now()]
                    self.targetTemps = [DEFAULT_TEMP]
                    logger.warning("Invalid date or time values; using default. Heating/cooling will NOT start")


                try:
                    if config["BeerTemperatureBuffer"] != "" and float(config["BeerTemperatureBuffer"]) >= 0.0:
                        self.bufferBeerTemp = float(config.get("BeerTemperatureBuffer"))
                    else:
                        raise Exception
                except:
                    self.bufferBeerTemp = DEFAULT_BUFFER_BEER_TEMP
                    logger.warning("Invalid beer temperature buffer in configuration; using default: "+str(self.bufferBeerTemp))

                try:
                    if config["ChamberScaleBuffer"] != "" and float(config["ChamberScaleBuffer"]) >= 0.0:
                            self.bufferChamberScale = float(config.get("ChamberScaleBuffer"))
                    else:
                        raise Exception
                except:
                    self.bufferChamberScale = DEFAULT_BUFFER_CHAMBER_SCALE
                    logger.warning("Invalid chamber scale buffer in configuration; using default: "+str(self.bufferChamberScale))

        except:
            logger.warning("Problem read from configuration file: "+CONFIGFILE)
       
            
        logger.debug("Chamber config updated")
