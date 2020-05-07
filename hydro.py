#! /usr/bin/env python3

import sys
import time
import os
import smbus
import configparser
import syslog
import string

from typing import NamedTuple

class HydroConfig(NamedTuple):
        i2c_port:       int
        i2c_address:    str
        units:          int

class UnitConfig(NamedTuple):
        light_relay:    str
        light_on:       int
        light_off:      int
        pump_relay:     str
        pump_on:        int
        pump_off:       int

unit_config = []
pump_counter = []

class Relay(object):
        def __init__(self, i2c_port, i2c_address):
                self.address =          i2c_address
                self.reg_mode1 =        0x06
                self.reg_data =         0xff
                self.bus =              smbus.SMBus(i2c_port)
                self.bus.write_byte_data(self.address, self.reg_mode1, self.reg_data)
        def on(self, relay):
                self.reg_data &=        ~(0x1 << (relay - 1))
                self.bus.write_byte_data(self.address, self.reg_mode1, self.reg_data)
        def off(self, relay):
                self.reg_data |=        (0x1 << (relay - 1))
                self.bus.write_byte_data(self.address, self.reg_mode1, self.reg_data)
        def allon(self):
                self.reg_data &=        ~(0xf << 0)
                self.bus.write_byte_data(self.address, self.reg_mode1, self.reg_data)
        def alloff(self):
                self.reg_data |=        (0xf << 0)
                self.bus.write_byte_data(self.address, self.reg_mode1, self.reg_data)

def custom_excepthook(type, value, traceback):
        syslog.syslog(syslog.LOG_INFO, 'Exit.')
        syslog.closelog()
        if type is KeyboardInterrupt:
                relay.alloff()
                return
        else:
                relay.alloff()
                sys.__excepthook__(type, value, traceback)

def read_config(config_file):
        config = configparser.RawConfigParser()
        config.read(config_file)
        config_parsed = HydroConfig     (
                        config.getint   ('global', 'i2c_port'),
                        config.get      ('global', 'i2c_address'),
                        config.getint   ('global', 'units')
                )

        for unit in list(range(config_parsed.units)):
                unit_config.append( UnitConfig (
                        config.getint   ('unit'+str(unit), 'light_relay'),
                        config.getint   ('unit'+str(unit), 'light_on'),
                        config.getint   ('unit'+str(unit), 'light_off'),
                        config.getint   ('unit'+str(unit), 'pump_relay'),
                        config.getint   ('unit'+str(unit), 'pump_on'),
                        config.getint   ('unit'+str(unit), 'pump_off')
                ) )
                pump_counter.append( 0 )
        timezone = config.get('global', 'timezone')
        if timezone:
                syslog.syslog(syslog.LOG_INFO, "Setting timezone to "+timezone)
                os.environ['TZ'] = timezone
        if not config_parsed.i2c_port:
                config_parsed.i2c_port = 1
        if not config_parsed.i2c_address:
                config_parsed.i2c_address = '0x20'
        return config_parsed

# Main loop here

if __name__=='__main__':
        syslog.openlog(ident='hydro', logoption=syslog.LOG_PID, facility=syslog.LOG_DAEMON)
        syslog.syslog(syslog.LOG_INFO, "Hydro daemon started")
        config = HydroConfig('', '', '')
        try:
                 config = read_config('./hydro.ini')
        except:
                 try: config = read_config('/usr/local/etc/hydro.ini')
                 except:
                        syslog.syslog(syslog.LOG_INFO, "No config")
                        print('No config')
                        sys.exit()
        syslog.syslog(syslog.LOG_INFO,
                "Relay device i2c-"+str(config.i2c_port)+" address "+config.i2c_address)
        relay = Relay(config.i2c_port, int(config.i2c_address, 16))

        sys.excepthook=custom_excepthook
        relay.alloff()
        time.sleep(5)   # Give the relays a few seconds to settle

        while True:
                now_hour = int(time.strftime("%H"))

                for unit in list(range(config.units)):
                  # Handle lights
                  do_light = (unit_config[unit].light_on <= now_hour < unit_config[unit].light_off)
                  if do_light:
                        syslog.syslog(syslog.LOG_INFO, "Lights on "+str(unit))
                        relay.on(unit_config[unit].light_relay)
                  else:
                        syslog.syslog(syslog.LOG_INFO, "Lights off "+str(unit))
                        relay.off(unit_config[unit].light_relay)

                  # Handle pumps
                  if pump_counter[unit] >= (unit_config[unit].pump_on + unit_config[unit].pump_off):
                        pump_counter[unit] = 0
                  if pump_counter[unit] < unit_config[unit].pump_on:
                        syslog.syslog(syslog.LOG_INFO, "Pump on "+str(unit))
                        relay.on(unit_config[unit].pump_relay)
                  else:
                        syslog.syslog(syslog.LOG_INFO, "Pump off "+str(unit))
                        relay.off(unit_config[unit].pump_relay)
                  pump_counter[unit] += 1

                time.sleep(60)
