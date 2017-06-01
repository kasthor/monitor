import unittest
from mock import patch, ANY, MagicMock
from unittest import TestCase

import monitor

class MonitorTests( TestCase ):
  @patch( "yaml.load" ) 
  def test_monitor_loads_the_configuration_file( self, yaml_load ):
    monitor.Monitor()
    self.assertTrue( yaml_load.called )

  @patch("monitor.ListenerFactory.create")
  @patch("yaml.load")
  def test_monitor_add_listeners_from_config( self, yaml_load, listener_create ):
    yaml_load.return_value = { 'listeners': [ { 'type': 'dummy' } ]}
    monitor.Monitor()
    listener_create.assert_called_with( { 'type': 'dummy' } )

  @patch("monitor.UnitFactory.create")
  @patch("yaml.load")
  def test_monitor_add_units_from_config( self, yaml_load, units_create ):
    yaml_load.return_value = { 'units': [ { 'proto': 'dummy' } ]}
    monitor.Monitor()
    units_create.assert_called_with( ANY, { 'proto': 'dummy' } )
    self.assertIsInstance( units_create.call_args[0][0], monitor.MainListener )

class UnitsTests( TestCase ):
  def setUp( self ):
    self.dummy_config = {
      'name': 'dummy',
      'proto': 'dummy',
      'fail_tolerance': 0,
      'fail_interval': 0,
      'check_interval': 1,
      'check_tolerance': 1
    }

    # A dummy listener
    self.listener_mock = MagicMock()

    # our dummy listener has a default emit method
    self.listener_mock.emit = MagicMock()

    # A default unit 
    self.unit = monitor.Unit( self.listener_mock, self.dummy_config )

    # The default unit returns true on probe
    self.unit.probe = MagicMock( return_value=True )
    
  def test_configures_its_name_and_defaults( self ):
    self.assertEqual( self.unit.name, "dummy" )
    self.assertEqual( self.unit.interval, 1 )
    self.assertIsInstance( self.unit.check_interval, int )
    self.assertIsInstance( self.unit.check_tolerance, int )
    self.assertIsInstance( self.unit.fail_interval, int )
    self.assertIsInstance( self.unit.fail_tolerance, int )
    self.assertIsInstance( self.unit.tolerance, int )

  def test_when_tick_at_the_begining_sends_check( self ):
    with patch( 'monitor.Unit.check' ) as mock_check:
      self.unit.tick()
      self.unit.check.assert_called_with()

  def test_when_tick_at_the_begining_emits_started( self ):
    self.unit.tick()
    self.unit.listener.emit.assert_called_with( ANY )
    self.assertEqual( self.unit.listener.emit.call_args[0][0].event, 'started')
    self.assertEqual( self.unit.interval, self.unit.check_interval )

  def test_when_tick_at_the_begining_emits_started_with_failure_if_failure( self ):
    self.unit.probe.return_value = False
    self.unit.tick()
    self.unit.listener.emit.assert_called_with( ANY )
    self.assertEqual( self.unit.listener.emit.call_args[0][0].event, 'started_with_failure')
    self.assertEqual( self.unit.interval, self.unit.fail_interval )

  def test_calls_check_only_after_interval( self ):
    with patch( 'monitor.Unit.check' ) as mock_check:
      self.unit.tick() #first tick always do check when just instantiated
      self.unit.check.called = False #so we reset the called state
      self.unit.tick() # interval of 1
      self.unit.tick() # check should be called here
      self.unit.check.assert_called_with()

  def test_emits_failure( self ):
    self.unit.status = self.unit.UP # Short-circuit to status UP
    self.unit.probe.return_value = False # probe returns failure state
    self.unit.tick()
    self.assertTrue(self.unit.listener.emit.called) # Tolerance meet, emit called

  def test_emits_failure_until_tolerance_is_meet( self ):
    self.unit.status = self.unit.UP # Short-circuit to status UP
    self.unit.fail_tolerance = 1
    self.unit.tick()
    self.unit.listener.emit.called = False # First tick always trigger
    self.unit.probe.return_value = False   # probe returns failure state
    self.unit.tick() # check interval of 1
    self.unit.tick() # relized it's down but no emit
    self.assertFalse(self.unit.listener.emit.called) # Not called until tolerance is meet
    self.unit.tick() # fail interval of 0 immediate test
    self.assertTrue(self.unit.listener.emit.called) # Tolerance meet, emit called

class RedisSetHashListenerTests( TestCase ):
  def setUp( self ):
    self.listener = monitor.RedisSetHashListener( {} )

  def test_when_receives_a_started_event_calls_set( self ):
    with patch( 'monitor.RedisSetHashListener.set_hash_for' ) as mock_set:
      event = monitor.Event( 'test', 'started' )
      self.listener.emit( event )
      self.assertTrue( mock_set.called )

  def test_when_receives_a_started_with_failure_event_calls_set( self ):
    with patch( 'monitor.RedisSetHashListener.del_hash_for' ) as mock_del:
      event = monitor.Event( 'test', 'started_with_failure' )
      self.listener.emit( event )
      self.assertTrue( mock_del.called )

  def test_when_receives_a_recovered_event_calls_set( self ):
    with patch( 'monitor.RedisSetHashListener.set_hash_for' ) as mock_set:
      event = monitor.Event( 'test', 'recovered' )
      self.listener.emit( event )
      self.assertTrue( mock_set.called )

  def test_when_receives_a_fail_event_calls_set( self ):
    with patch( 'monitor.RedisSetHashListener.del_hash_for' ) as mock_del:
      event = monitor.Event( 'test', 'fail' )
      self.listener.emit( event )
      self.assertTrue( mock_del.called )

if __name__ == '__main__':
  unittest.main()
