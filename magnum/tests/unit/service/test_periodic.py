# Copyright 2015 Intel, Inc
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from heatclient import exc as heat_exc
import mock

from magnum.common import context
from magnum.common.rpc_service import CONF
from magnum.db.sqlalchemy import api as dbapi
from magnum import objects
from magnum.objects.fields import BayStatus as bay_status
from magnum.service import periodic
from magnum.tests import base
from magnum.tests.unit.db import utils


class fake_stack(object):
    def __init__(self, **kw):
        for key, val in kw.items():
            setattr(self, key, val)


class PeriodicTestCase(base.TestCase):

    def setUp(self):
        super(PeriodicTestCase, self).setUp()

        ctx = context.make_admin_context()

        # Can be identical for all bays.
        trust_attrs = {
            'trustee_username': '5d12f6fd-a196-4bf0-ae4c-1f639a523a52',
            'trustee_password': 'ain7einaebooVaig6d',
            'trust_id': '39d920ca-67c6-4047-b57a-01e9e16bb96f',
            }

        trust_attrs.update({'id': 1, 'stack_id': '11',
                           'status': bay_status.CREATE_IN_PROGRESS})
        bay1 = utils.get_test_bay(**trust_attrs)
        trust_attrs.update({'id': 2, 'stack_id': '22',
                           'status': bay_status.DELETE_IN_PROGRESS})
        bay2 = utils.get_test_bay(**trust_attrs)
        trust_attrs.update({'id': 3, 'stack_id': '33',
                           'status': bay_status.UPDATE_IN_PROGRESS})
        bay3 = utils.get_test_bay(**trust_attrs)
        trust_attrs.update({'id': 4, 'stack_id': '44',
                           'status': bay_status.CREATE_COMPLETE})
        bay4 = utils.get_test_bay(**trust_attrs)
        trust_attrs.update({'id': 5, 'stack_id': '55',
                           'status': bay_status.ROLLBACK_IN_PROGRESS})
        bay5 = utils.get_test_bay(**trust_attrs)

        self.bay1 = objects.Bay(ctx, **bay1)
        self.bay2 = objects.Bay(ctx, **bay2)
        self.bay3 = objects.Bay(ctx, **bay3)
        self.bay4 = objects.Bay(ctx, **bay4)
        self.bay5 = objects.Bay(ctx, **bay5)

    @mock.patch.object(objects.Bay, 'list')
    @mock.patch('magnum.common.clients.OpenStackClients')
    @mock.patch.object(dbapi.Connection, 'destroy_bay')
    @mock.patch.object(dbapi.Connection, 'update_bay')
    def test_sync_bay_status_changes(self, mock_db_update, mock_db_destroy,
                                     mock_oscc, mock_bay_list):
        mock_heat_client = mock.MagicMock()
        stack1 = fake_stack(id='11', stack_status=bay_status.CREATE_COMPLETE,
                            stack_status_reason='fake_reason_11')
        stack3 = fake_stack(id='33', stack_status=bay_status.UPDATE_COMPLETE,
                            stack_status_reason='fake_reason_33')
        stack5 = fake_stack(id='55', stack_status=bay_status.ROLLBACK_COMPLETE,
                            stack_status_reason='fake_reason_55')
        mock_heat_client.stacks.list.return_value = [stack1, stack3, stack5]
        get_stacks = {'11': stack1, '33': stack3, '55': stack5}

        def stack_get_sideefect(arg):
            if arg == '22':
                raise heat_exc.HTTPNotFound
            return get_stacks[arg]

        mock_heat_client.stacks.get.side_effect = stack_get_sideefect
        mock_osc = mock_oscc.return_value
        mock_osc.heat.return_value = mock_heat_client
        mock_bay_list.return_value = [self.bay1, self.bay2, self.bay3,
                                      self.bay5]

        mock_keystone_client = mock.MagicMock()
        mock_keystone_client.client.project_id = "fake_project"
        mock_osc.keystone.return_value = mock_keystone_client

        periodic.MagnumPeriodicTasks(CONF).sync_bay_status(None)

        self.assertEqual(bay_status.CREATE_COMPLETE, self.bay1.status)
        self.assertEqual('fake_reason_11', self.bay1.status_reason)
        mock_db_destroy.assert_called_once_with(self.bay2.uuid)
        self.assertEqual(bay_status.UPDATE_COMPLETE, self.bay3.status)
        self.assertEqual('fake_reason_33', self.bay3.status_reason)
        self.assertEqual(bay_status.ROLLBACK_COMPLETE, self.bay5.status)
        self.assertEqual('fake_reason_55', self.bay5.status_reason)

    @mock.patch.object(objects.Bay, 'list')
    @mock.patch('magnum.common.clients.OpenStackClients')
    def test_sync_auth_fail(self, mock_oscc, mock_bay_list):
        """Tests handling for unexpected exceptions in _get_bay_stacks()

        It does this by raising an a HTTPUnauthorized exception in Heat client.
        The affected stack thus missing from the stack list should not lead to
        bay state changing in this case. Likewise, subsequent bays should still
        change state, despite the affected bay being skipped.
        """
        stack1 = fake_stack(id='11',
                            stack_status=bay_status.CREATE_COMPLETE)

        mock_heat_client = mock.MagicMock()

        def stack_get_sideefect(arg):
            raise heat_exc.HTTPUnauthorized

        mock_heat_client.stacks.get.side_effect = stack_get_sideefect
        mock_heat_client.stacks.list.return_value = [stack1]
        mock_osc = mock_oscc.return_value
        mock_osc.heat.return_value = mock_heat_client
        mock_bay_list.return_value = [self.bay1]
        periodic.MagnumPeriodicTasks(CONF).sync_bay_status(None)

        self.assertEqual(bay_status.CREATE_IN_PROGRESS, self.bay1.status)

    @mock.patch.object(objects.Bay, 'list')
    @mock.patch('magnum.common.clients.OpenStackClients')
    def test_sync_bay_status_not_changes(self, mock_oscc, mock_bay_list):
        mock_heat_client = mock.MagicMock()
        stack1 = fake_stack(id='11',
                            stack_status=bay_status.CREATE_IN_PROGRESS)
        stack2 = fake_stack(id='22',
                            stack_status=bay_status.DELETE_IN_PROGRESS)
        stack3 = fake_stack(id='33',
                            stack_status=bay_status.UPDATE_IN_PROGRESS)
        stack5 = fake_stack(id='55',
                            stack_status=bay_status.ROLLBACK_IN_PROGRESS)
        get_stacks = {'11': stack1, '22': stack2, '33': stack3, '55': stack5}

        def stack_get_sideefect(arg):
            if arg == '22':
                raise heat_exc.HTTPNotFound
            return get_stacks[arg]

        mock_heat_client.stacks.get.side_effect = stack_get_sideefect
        mock_heat_client.stacks.list.return_value = [stack1, stack2, stack3,
                                                     stack5]
        mock_osc = mock_oscc.return_value
        mock_osc.heat.return_value = mock_heat_client
        mock_bay_list.return_value = [self.bay1, self.bay2, self.bay3,
                                      self.bay5]
        periodic.MagnumPeriodicTasks(CONF).sync_bay_status(None)

        self.assertEqual(bay_status.CREATE_IN_PROGRESS, self.bay1.status)
        self.assertEqual(bay_status.DELETE_IN_PROGRESS, self.bay2.status)
        self.assertEqual(bay_status.UPDATE_IN_PROGRESS, self.bay3.status)
        self.assertEqual(bay_status.ROLLBACK_IN_PROGRESS, self.bay5.status)

    @mock.patch.object(objects.Bay, 'list')
    @mock.patch('magnum.common.clients.OpenStackClients')
    @mock.patch.object(dbapi.Connection, 'destroy_bay')
    @mock.patch.object(dbapi.Connection, 'update_bay')
    def test_sync_bay_status_heat_not_found(self, mock_db_update,
                                            mock_db_destroy, mock_oscc,
                                            mock_bay_list):
        mock_heat_client = mock.MagicMock()
        mock_heat_client.stacks.list.return_value = []
        mock_osc = mock_oscc.return_value
        mock_osc.heat.return_value = mock_heat_client
        mock_bay_list.return_value = [self.bay1, self.bay2, self.bay3]

        mock_keystone_client = mock.MagicMock()
        mock_keystone_client.client.project_id = "fake_project"
        mock_osc.keystone.return_value = mock_keystone_client

        periodic.MagnumPeriodicTasks(CONF).sync_bay_status(None)

        self.assertEqual(bay_status.CREATE_FAILED, self.bay1.status)
        self.assertEqual('Stack with id 11 not found in Heat.',
                         self.bay1.status_reason)
        mock_db_destroy.assert_called_once_with(self.bay2.uuid)
        self.assertEqual(bay_status.UPDATE_FAILED, self.bay3.status)
        self.assertEqual('Stack with id 33 not found in Heat.',
                         self.bay3.status_reason)

    @mock.patch('magnum.conductor.monitors.create_monitor')
    @mock.patch('magnum.objects.Bay.list')
    @mock.patch('magnum.common.rpc.get_notifier')
    @mock.patch('magnum.common.context.make_admin_context')
    def test_send_bay_metrics(self, mock_make_admin_context, mock_get_notifier,
                              mock_bay_list, mock_create_monitor):
        """Test if RPC notifier receives the expected message"""
        mock_make_admin_context.return_value = self.context
        notifier = mock.MagicMock()
        mock_get_notifier.return_value = notifier
        mock_bay_list.return_value = [self.bay1, self.bay2, self.bay3,
                                      self.bay4]
        monitor = mock.MagicMock()
        monitor.get_metric_names.return_value = ['metric1', 'metric2']
        monitor.compute_metric_value.return_value = 30
        monitor.get_metric_unit.return_value = '%'
        mock_create_monitor.return_value = monitor

        periodic.MagnumPeriodicTasks(CONF)._send_bay_metrics(self.context)

        expected_event_type = 'magnum.bay.metrics.update'
        expected_metrics = [
            {
                'name': 'metric1',
                'value': 30,
                'unit': '%',
            },
            {
                'name': 'metric2',
                'value': 30,
                'unit': '%',
            },
        ]
        expected_msg = {
            'user_id': self.bay4.user_id,
            'project_id': self.bay4.project_id,
            'resource_id': self.bay4.uuid,
            'metrics': expected_metrics
        }

        self.assertEqual(1, mock_create_monitor.call_count)
        notifier.info.assert_called_once_with(
            self.context, expected_event_type, expected_msg)

    @mock.patch('magnum.conductor.monitors.create_monitor')
    @mock.patch('magnum.objects.Bay.list')
    @mock.patch('magnum.common.rpc.get_notifier')
    @mock.patch('magnum.common.context.make_admin_context')
    def test_send_bay_metrics_compute_metric_raise(
            self, mock_make_admin_context, mock_get_notifier, mock_bay_list,
            mock_create_monitor):
        mock_make_admin_context.return_value = self.context
        notifier = mock.MagicMock()
        mock_get_notifier.return_value = notifier
        mock_bay_list.return_value = [self.bay4]
        monitor = mock.MagicMock()
        monitor.get_metric_names.return_value = ['metric1', 'metric2']
        monitor.compute_metric_value.side_effect = Exception(
            "error on computing metric")
        mock_create_monitor.return_value = monitor

        periodic.MagnumPeriodicTasks(CONF)._send_bay_metrics(self.context)

        expected_event_type = 'magnum.bay.metrics.update'
        expected_msg = {
            'user_id': self.bay4.user_id,
            'project_id': self.bay4.project_id,
            'resource_id': self.bay4.uuid,
            'metrics': []
        }
        self.assertEqual(1, mock_create_monitor.call_count)
        notifier.info.assert_called_once_with(
            self.context, expected_event_type, expected_msg)

    @mock.patch('magnum.conductor.monitors.create_monitor')
    @mock.patch('magnum.objects.Bay.list')
    @mock.patch('magnum.common.rpc.get_notifier')
    @mock.patch('magnum.common.context.make_admin_context')
    def test_send_bay_metrics_pull_data_raise(
            self, mock_make_admin_context, mock_get_notifier, mock_bay_list,
            mock_create_monitor):
        mock_make_admin_context.return_value = self.context
        notifier = mock.MagicMock()
        mock_get_notifier.return_value = notifier
        mock_bay_list.return_value = [self.bay4]
        monitor = mock.MagicMock()
        monitor.pull_data.side_effect = Exception("error on pulling data")
        mock_create_monitor.return_value = monitor

        periodic.MagnumPeriodicTasks(CONF)._send_bay_metrics(self.context)

        self.assertEqual(1, mock_create_monitor.call_count)
        self.assertEqual(0, notifier.info.call_count)

    @mock.patch('magnum.conductor.monitors.create_monitor')
    @mock.patch('magnum.objects.Bay.list')
    @mock.patch('magnum.common.rpc.get_notifier')
    @mock.patch('magnum.common.context.make_admin_context')
    def test_send_bay_metrics_monitor_none(
            self, mock_make_admin_context, mock_get_notifier, mock_bay_list,
            mock_create_monitor):
        mock_make_admin_context.return_value = self.context
        notifier = mock.MagicMock()
        mock_get_notifier.return_value = notifier
        mock_bay_list.return_value = [self.bay4]
        mock_create_monitor.return_value = None

        periodic.MagnumPeriodicTasks(CONF)._send_bay_metrics(self.context)

        self.assertEqual(1, mock_create_monitor.call_count)
        self.assertEqual(0, notifier.info.call_count)
