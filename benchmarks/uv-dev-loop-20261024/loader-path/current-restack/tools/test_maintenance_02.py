import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import maintenance_02 as maintenance
import restack_control_02 as restack_control

def observation():
    return {'monotonic_us': 0, 'services': {
        name: {
            'timer': {'Id': name + '.timer', 'LoadState': 'loaded', 'ActiveState': 'active', 'NextElapseUSecMonotonic': '5min', 'LastTriggerUSecMonotonic': '1s', 'TimersMonotonic': 'OnUnitInactiveUSec=5min'},
            'service': {'Id': name + '.service', 'LoadState': 'loaded', 'ActiveState': 'inactive', 'SubState': 'dead', 'ExecMainStartTimestampMonotonic': '1000000', 'ExecMainExitTimestampMonotonic': '2000000', 'CPUUsageNSec': '1000'},
        } for name in maintenance.HEAVY}}

class MaintenanceTests(unittest.TestCase):
    def test_complete_pair_fits(self):
        self.assertTrue(maintenance.ready(observation(), 180))

    def test_insufficient_window_refuses(self):
        self.assertFalse(maintenance.ready(observation(), 301))

    def test_unavailable_deadline_waits(self):
        for value in ('', '-', 'n/a', 'infinity', '0', '0us', '18446744073709551615', '18446744073709551615us'):
            row = observation()
            row['services'][maintenance.HEAVY[2]]['timer']['NextElapseUSecMonotonic'] = value
            self.assertFalse(maintenance.ready(row, 180), value)

    def test_third_service_active_waits(self):
        row = observation()
        row['services'][maintenance.HEAVY[2]]['service'].update(ActiveState='activating', SubState='start')
        self.assertFalse(maintenance.ready(row, 180))

    def test_wrong_service_identity_rejects(self):
        row = observation()
        row['services'][maintenance.HEAVY[2]]['service']['Id'] = 'different.service'
        with self.assertRaises(AssertionError):
            maintenance.ready(row, 180)

    def test_cycle_inside_pair_rejects(self):
        before = observation()
        after = copy.deepcopy(before)
        after['services'][maintenance.HEAVY[2]]['service']['ExecMainStartTimestampMonotonic'] = '3000000'
        with self.assertRaises(AssertionError):
            restack_control.same_service_cycle(before, after)

    def test_active_service_at_command_boundary_rejects(self):
        before = observation()
        after = copy.deepcopy(before)
        after['services'][maintenance.HEAVY[0]]['service'].update(ActiveState='active', SubState='running')
        with self.assertRaises(AssertionError):
            restack_control.same_service_cycle(before, after)

    def test_cpu_accounting_is_retained_but_not_a_false_new_cycle(self):
        before = observation()
        after = copy.deepcopy(before)
        after['services'][maintenance.HEAVY[0]]['service']['CPUUsageNSec'] = '1001'
        restack_control.same_service_cycle(before, after)


class TimerPropertyTests(unittest.TestCase):
    def test_repeated_timer_values_are_preserved(self):
        text = 'Id=example.timer\nTimersMonotonic={ OnUnitInactiveUSec=5min ; next_elapse=10min }\nTimersMonotonic={ OnBootUSec=5min ; next_elapse=5min }\n'
        row = maintenance.parse_properties(text, ['Id', 'TimersMonotonic'])
        self.assertEqual(row['TimersMonotonic'], ['{ OnUnitInactiveUSec=5min ; next_elapse=10min }', '{ OnBootUSec=5min ; next_elapse=5min }'])

    def test_duplicate_scalar_rejected(self):
        with self.assertRaises(AssertionError):
            maintenance.parse_properties('Id=one\nId=two\n', ['Id'])

    def test_unknown_or_missing_property_rejected(self):
        for text in ('Id=one\nUnknown=value\n', ''):
            with self.assertRaises(AssertionError):
                maintenance.parse_properties(text, ['Id'])

if __name__ == '__main__':
    unittest.main()
