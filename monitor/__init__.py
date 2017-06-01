#!/usr/bin/env python

from httplib import HTTPConnection
from urlparse import urlparse
from time import sleep
from os import path
from slackclient import SlackClient
import yaml, socket, json
import redis

class InvalidProtocol(Exception): pass
class InvalidListenerType(Exception): pass
class ConfigurationException(Exception): pass

class Event( object ):
  def __init__( self, name, event ):
    self.name = name
    self.event = event

  def __str__( self ):
    messages = {
      'started': 'monitor for %s has started successfuly',
      'started_with_failure': 'monitor for %s has started but server is down',
      'fail': "server %s is down!",
      'recovered': "server %s has recovered"
    }

    return messages[ self.event ] % self.name


class Monitor( object ):
  CONFIG_FILE_PATHS=['./monitor.yaml', '~/.monitor.yaml', '/etc/monitor/config.yaml']

  def __init__( self ):
    self.config()
    self.setup_listeners()
    self.setup_units()

  def config( self ):
    for cfg in self.CONFIG_FILE_PATHS:
      if path.isfile( cfg ):
        with open( cfg ) as config: self.config = yaml.load( config )
        break

  def setup_listeners( self ):
    self.listener = MainListener()
    for listener_config in self.config.get('listeners', [] ):
      self.listener.add(
        ListenerFactory.create( listener_config )
      )

  def setup_units( self ):
    self.units = []
    for unit_config in self.config.get('units', [] ):
      self.units.append(
        UnitFactory.create( self.listener, unit_config )
      )

  def loop( self ):
    while True:
      for unit in self.units:
        unit.tick()
      sleep( 1 )

# Listeners
class ListenerFactory( object ):
  @classmethod
  def create( self, config ):
    if config['type'] == 'console':
      return ConsoleListener( config )
    if config['type'] == 'redis_hash':
      return RedisSetHashListener( config )
    if config['type'] == 'slack':
      return SlackListener( config )
    else:
      raise InvalidListenerType( "Listener of type '%s' not found" % config['type'] )

class Listener( object ):

  def __init__( self, config={} ):
    self.config = config

  def emit( self, event ):
    raise NotImplementedError()

class MainListener( Listener ):
  listeners = []

  def add( self, listener ):
    self.listeners.append( listener )

  def emit( self, event ):
    for listener in self.listeners:
      listener.emit( event )

class ConsoleListener( Listener ):
  def emit( self, event ):
    print str( event )

class SlackListener( Listener ):
  def __init__( self, config ):
    super(SlackListener, self).__init__(config)
    if not self.config.get('token', None): raise ConfigurationException( 'Key: %s is required for slack configuration' % 'token' )

    self.channel = self.config.get("channel", "#monitor")
    self.username = self.config.get("username", "monitor")
    self.emoji = self.config.get("emoji", ":robot_face:")
    self.slack = SlackClient( self.config['token'] )

  def emit( self, event ):
    self.slack.api_call( 'chat.postMessage', channel=self.channel, username=self.username, icon_emoji=self.emoji, text=str(event) )

class RedisSetHashListener( Listener ):
  def __init__( self, config ):
    super( RedisSetHashListener, self ).__init__( config )
    self.redis_url = urlparse( self.config.get('server_url', 'redis://localhost:6379') )
    self.redis = redis.StrictRedis( self.redis_url.hostname, port=self.redis_url.port, password=self.redis_url.password )
    self.hash_name = self.config.get( 'hash_name', 'availability' )

  def emit( self, event ):
    if event.event == 'started' or event.event == 'recovered':
      self.set_hash_for( event.name )
    else:
      self.del_hash_for( event.name )

  def set_hash_for( self, name ):
    self.redis.hset( self.hash_name, name, self.get_json_for( name ) )

  def del_hash_for( self, name ):
    self.redis.hdel( self.hash_name, name )

  def get_json_for( self, name ):
    unit_data = self.config.get('unit_data', {})
    return json.dumps( unit_data.get( name, {"server": name } ) )

# Factory 

class UnitFactory(object):
  @classmethod
  def create( self, listener, config ):
    proto = config['proto']

    if proto == 'http':
      return HTTPUnit.create( listener, config )
    else:
      raise InvalidProtocol()

# Units

class Unit(object):
  UP = True
  DOWN = False

  @classmethod
  def create( self, listener, config ):
    return self( listener, config )

  def __init__( self, listener, config ):
    self.status = None
    self.listener = listener
    self.configure( config )
    self.interval = 1

  def configure( self, config ):
    self.name            = config['name']
    self.check_interval  = config.get( 'check_interval',   5 )
    self.check_tolerance = config.get( 'check_tolerance',  1 )
    self.fail_interval   = config.get( 'fail_interval',    1 )
    self.fail_tolerance  = config.get( 'fail_tolerance',   1 )
    self.tolerance = -1

  def emit( self, event ):
    self.listener.emit( Event( self.name, event ) )
    self.emit_status = self.status

  def tick( self ):
    self.interval -= 1

    if self.interval <= 0: self.check()

  def check( self ):
    status = self.probe()

    if status != self.status:
      if status == self.UP:
        if self.status == None:
          self.status = status
          self.emit( 'started' )
        else:
          self.tolerance = self.check_tolerance
      elif status == self.DOWN:
        if self.status == None:
          self.status = status
          self.emit( 'started_with_failure' )
        else:
          self.tolerance = self.fail_tolerance

    if self.tolerance == 0 or status == self.status:
      if self.tolerance == 0: self.emit( 'fail' if self.status == self.DOWN else 'recovered' )
      if self.tolerance >= 0: self.tolerance -= 1

    self.status = status
    self.interval = self.check_interval if self.emit_status == self.UP and self.status == self.UP else self.fail_interval

  def probe( self ):
    raise NotImplementedError()

class HTTPUnit(Unit):
  def __init__( self, listener, options ):
    super( HTTPUnit, self ).__init__( listener, options )
    self.url = urlparse( options.get('url') )

  def probe( self ):
    return self.get_http_status() == 200

  def get_http_status( self ):
    try:
      conn = HTTPConnection( self.url.hostname )
      conn.request( 'HEAD', self.url.path )
      response = conn.getresponse()
      return getattr( response, 'status', 0 )
    except:
      return 0

def main():
  Monitor().loop()


if( __name__ == '__main__' ): main()
