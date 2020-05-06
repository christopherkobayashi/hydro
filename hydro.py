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
	on_hour:		int
	off_hour:		int
	light_relay:	str
	pump_on:		int
	pump_off:		int
	pump_relay:		str
	i2c_port:		int
	i2c_address:	str

class Relay(object):
	def __init__(self, i2c_port, i2c_address):
		self.address =		i2c_address
		self.reg_mode1 =	0x06
		self.reg_data =		0xff
		self.bus =			smbus.SMBus(i2c_port)
		self.bus.write_byte_data(self.address, self.reg_mode1, self.reg_data)
	def on(self, relay):
		self.reg_data &=	~(0x1 << (relay - 1))
		self.bus.write_byte_data(self.address, self.reg_mode1, self.reg_data)
	def off(self, relay):
		self.reg_data |=	(0x1 << (relay - 1))
		self.bus.write_byte_data(self.address, self.reg_mode1, self.reg_data)
	def allon(self):
		self.reg_data &=	~(0xf << 0)
		self.bus.write_byte_data(self.address, self.reg_mode1, self.reg_data)
	def alloff(self):
		self.reg_data |=	(0xf << 0)
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
	config_parsed = HydroConfig	(
			config.getint	('lights', 'on'),
			config.getint	('lights', 'off'),
			config.get		('lights', 'relay'),
			config.getint	('pump', 'on'),
			config.getint	('pump', 'off'),
			config.get		('pump', 'relay'),
			config.getint	('global', 'i2c_port'),
			config.get		('global', 'i2c_address')
		)
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
	config = HydroConfig('', '', '', '', '', '', '', '')
	config = read_config('/usr/local/etc/hydro.ini')
	syslog.syslog(syslog.LOG_INFO,
		"Relay device i2c-"+str(config.i2c_port)+" address "+config.i2c_address)
	relay = Relay(config.i2c_port, int(config.i2c_address, 16))

	pump_counter = 0

	sys.excepthook=custom_excepthook
	relay.alloff()
	time.sleep(5)	# Give the relays a few seconds to settle

	while True:
		now_hour = int(time.strftime("%H"))

		# Handle lights
		do_light = (config.on_hour <= now_hour < config.off_hour)
		if do_light:
			for r in config.light_relay.split():
				syslog.syslog(syslog.LOG_INFO, "Lights on "+r)
				relay.on(int(r))
		else:
			for r in config.light_relay.split():
				syslog.syslog(syslog.LOG_INFO, "Lights off "+r)
				relay.off(int(r))

		# Handle pumps
		if pump_counter >= (config.pump_on + config.pump_off):
			pump_counter = 0
		if pump_counter < config.pump_on:
			for r in config.pump_relay.split():
				syslog.syslog(syslog.LOG_INFO, "Pump on "+r)
				relay.on(int(r))
		else:
			syslog.syslog(syslog.LOG_INFO, "Pump off")
			for r in config.pump_relay.split():
				syslog.syslog(syslog.LOG_INFO, "Pump off "+r)
				relay.off(int(r))
		pump_counter += 1

		time.sleep(60)
