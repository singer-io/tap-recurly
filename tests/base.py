import tap_tester.connections as connections
import tap_tester.menagerie as menagerie
import tap_tester.runner as runner

import os
from datetime import datetime, time, date, timezone, timedelta
import unittest
from functools import reduce
from singer import utils
from singer import metadata


class RecurlyBaseTest(unittest.TestCase):


    def setUp(self):
        missing_envs = [x for x in [os.getenv('TAP_RECURLY_SUBDOMAIN'),
                                os.getenv('TAP_RECURLY_API_KEY'),
                                os.getenv('TAP_RECURLY_START_DATE'),
                                os.getenv('TAP_RECURLY_QUOTA_LIMIT')] if x == None]
        if len(missing_envs) != 0:
            #pylint: disable=line-too-long
            raise Exception("set TAP_RECURLY_SUBDOMAIN, TAP_RECURLY_API_KEY, TAP_RECURLY_START_DATE, TAP_RECURLY_QUOTA_LIMIT")

        self.conn_id = connections.ensure_connection(self)


    def tap_name(self):
        return "tap-recurly"


    def get_type(self):
        return "platform.recurly"


    def get_credentials(self):
        return {'api_key': os.getenv('TAP_RECURLY_API_KEY')}


    def get_properties(self):
        return {'subdomain': os.getenv('TAP_RECURLY_SUBDOMAIN'), 
                'start_date': os.getenv('TAP_RECURLY_START_DATE'),
                'quota_limit': os.getenv('TAP_RECURLY_QUOTA_LIMIT')}


    def expected_sync_streams(self):
        return {
            'accounts',
            'billing_info',
            'adjustments',
            'coupon_redemptions',
            'coupons',
            'invoices',
            'plans',
            'plans_add_ons',
            'subscriptions',
            'transactions'
        }


    def expected_replication_method(self):
        return {
            'accounts': 'INCREMENTAL',
            'billing_info': 'INCREMENTAL',
            'adjustments': 'INCREMENTAL',
            'coupon_redemptions': 'INCREMENTAL',
            'coupons': 'INCREMENTAL',
            'invoices': 'INCREMENTAL',
            'plans': 'INCREMENTAL',
            'plans_add_ons': 'INCREMENTAL',
            'subscriptions': 'INCREMENTAL',
            'transactions': 'INCREMENTAL'
        }


    def expected_pks(self):
        return {
            'accounts': {'id'},
            'billing_info': {'account_id'},
            'adjustments': {'id'},
            'coupon_redemptions': {'id'},
            'coupons': {'id'},
            'invoices': {'id'},
            'plans': {'id'},
            'plans_add_ons': {'id'},
            'subscriptions': {'id'},
            'transactions': {'id'}
        }


    def expected_rks(self):
        return {
            'accounts': {'updated_at'},
            'billing_info': {'updated_at'},
            'adjustments': {'updated_at'},
            'coupon_redemptions': {'created_at'},
            'coupons': {'updated_at'},
            'invoices': {'updated_at'},
            'plans': {'updated_at'},
            'plans_add_ons': {'updated_at'},
            'subscriptions': {'updated_at'},
            'transactions': {'collected_at'}
        }


    def run_sync(self, conn_id):
        """
        Run a sync job and make sure it exited properly.
        Return a dictionary with keys of streams synced
        and values of records synced for each stream
        """
        # Run a sync job using orchestrator
        sync_job_name = runner.run_sync_mode(self, conn_id)

        # Verify tap and target exit codes
        exit_status = menagerie.get_exit_status(conn_id, sync_job_name)
        menagerie.verify_sync_exit_status(self, exit_status, sync_job_name)

        # Verify actual rows were synced
        sync_record_count = runner.examine_target_output_file(
            self, conn_id, self.expected_sync_streams(), self.expected_pks())
        return sync_record_count


    def min_bookmarks_by_stream(self, sync_records):
        """Return the minimum value for the replication key for each stream"""
        min_bookmarks = {}
        for stream, batch in sync_records.items():

            upsert_messages = [m for m in batch.get('messages') if m['action'] == 'upsert']
            stream_bookmark_key = self.expected_rks().get(stream, set())
            assert len(stream_bookmark_key) == 1  # There shouldn't be a compound replication key
            (stream_bookmark_key, ) = stream_bookmark_key

            bk_values = [message["data"].get(stream_bookmark_key) for message in upsert_messages]
            min_bookmarks[stream] = {stream_bookmark_key: None}
            for bk_value in bk_values:
                if bk_value is None:
                    continue

                if min_bookmarks[stream][stream_bookmark_key] is None:
                    min_bookmarks[stream][stream_bookmark_key] = bk_value

                if bk_value < min_bookmarks[stream][stream_bookmark_key]:
                    min_bookmarks[stream][stream_bookmark_key] = bk_value
        return min_bookmarks


    def max_bookmarks_by_stream(self, sync_records):
        """
        Return the maximum value for the replication key for each stream
        which is the bookmark expected value.
        Comparisons are based on the class of the bookmark value. Dates will be
        string compared which works for ISO date-time strings
        """
        max_bookmarks = {}
        for stream, batch in sync_records.items():

            upsert_messages = [m for m in batch.get('messages') if m['action'] == 'upsert']
            stream_bookmark_key = self.expected_rks().get(stream, set())

            assert len(stream_bookmark_key) == 1  # There shouldn't be a compound replication key
            stream_bookmark_key = stream_bookmark_key.pop()

            bk_values = [message["data"].get(stream_bookmark_key) for message in upsert_messages]
            max_bookmarks[stream] = {stream_bookmark_key: None}
            for bk_value in bk_values:
                if bk_value is None:
                    continue

                if max_bookmarks[stream][stream_bookmark_key] is None:
                    max_bookmarks[stream][stream_bookmark_key] = bk_value

                if bk_value > max_bookmarks[stream][stream_bookmark_key]:
                    max_bookmarks[stream][stream_bookmark_key] = bk_value
        return max_bookmarks


