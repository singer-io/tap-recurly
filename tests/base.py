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

    AUTOMATIC_FIELDS = "automatic"
    REPLICATION_KEYS = "valid-replication-keys"
    PRIMARY_KEYS = "table-key-properties"
    REPLICATION_METHOD = "forced-replication-method"
    INCREMENTAL = "INCREMENTAL"
    FULL_TABLE = "FULL_TABLE"
    START_DATE_FORMAT = "%Y-%m-%dT00:00:00Z"
    BOOKMARK_KEY_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
    REPLICATION_KEY_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
    start_date = ""

    def setUp(self):
        missing_envs = [x for x in [os.getenv('TAP_RECURLY_SUBDOMAIN'),
                                os.getenv('TAP_RECURLY_API_KEY'),
                                os.getenv('TAP_RECURLY_START_DATE'),
                                os.getenv('TAP_RECURLY_QUOTA_LIMIT')] if x == None]
        if len(missing_envs) != 0:
            #pylint: disable=line-too-long
            raise Exception("set TAP_RECURLY_SUBDOMAIN, TAP_RECURLY_API_KEY, TAP_RECURLY_START_DATE, TAP_RECURLY_QUOTA_LIMIT")

    @staticmethod
    def tap_name():
        return "tap-recurly"

    @staticmethod
    def get_type():
        return "platform.recurly"

    @staticmethod
    def get_credentials():
        return {'api_key': os.getenv('TAP_RECURLY_API_KEY')}

    def get_properties(self): # TODO
        return {'subdomain': os.getenv('TAP_RECURLY_SUBDOMAIN'),
                'start_date': os.getenv('TAP_RECURLY_START_DATE'),
                'quota_limit': os.getenv('TAP_RECURLY_QUOTA_LIMIT')}

    def expected_metadata(self):
        return {
            'accounts': {
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"updated_at"},
            },
            'adjustments': {
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"updated_at"},
            },
            'billing_info': {  # custom fields supported
                self.PRIMARY_KEYS: {"account_id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"updated_at"},
            },
            'coupons': {
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"updated_at"},
            },
            'coupon_redemptions': {  # undocumented TODO
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"created_at"},
            },
            'invoices': {
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"updated_at"},
            },
            'plans': {
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"updated_at"},
            },
            'plans_add_ons': {
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"updated_at"},
            },
            'subscriptions': {  # custom fields supported
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"updated_at"},
            },
            'transactions': {
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"collected_at"},
            },
            'usages': {
                self.PRIMARY_KEYS: {"id"},
                self.REPLICATION_METHOD: self.INCREMENTAL,
                self.REPLICATION_KEYS: {"recording_timestamp"},
            },
        }

    def expected_streams(self):
        return set(self.expected_metadata().keys())

    def expected_primary_keys(self):
        """
        return a dictionary with key of table name
        and value as a set of primary key fields
        """
        return {table: properties.get(self.PRIMARY_KEYS, set())
                for table, properties
                in self.expected_metadata().items()}

    def expected_replication_keys(self):
        """
        return a dictionary with key of table name
        and value as a set of replication key fields
        """
        return {table: properties.get(self.REPLICATION_KEYS, set())
                for table, properties
                in self.expected_metadata().items()}

    def expected_replication_method(self):
        """return a dictionary with key of table name nd value of replication method"""
        return {table: properties.get(self.REPLICATION_METHOD, None)
                for table, properties
                in self.expected_metadata().items()}

    @staticmethod
    def select_all_streams_and_fields(conn_id, catalogs, select_all_fields: bool = True):
        """Select all streams and all fields within streams"""
        for catalog in catalogs:
            schema = menagerie.get_annotated_schema(conn_id, catalog['stream_id'])

            non_selected_properties = []
            if not select_all_fields:
                # get a list of all properties so that none are selected
                non_selected_properties = schema.get('annotated-schema', {}).get(
                    'properties', {}).keys()

            connections.select_catalog_and_fields_via_metadata(
                conn_id, catalog, schema, [], non_selected_properties)

    def run_and_verify_check_mode(self, conn_id):
        """
        Run the tap in check mode and verify it succeeds.
        This should be ran prior to field selection and initial sync.

        Return the connection id and found catalogs from menagerie.
        """
        # run in check mode
        check_job_name = runner.run_check_mode(self, conn_id)

        # verify check exit codes
        exit_status = menagerie.get_exit_status(conn_id, check_job_name)
        menagerie.verify_check_exit_status(self, exit_status, check_job_name)

        found_catalogs = menagerie.get_catalogs(conn_id)
        self.assertGreater(len(found_catalogs), 0, msg="No catalog produced.")

        found_catalog_names = {found_catalog['stream_name'] for found_catalog in found_catalogs}
        self.assertSetEqual(self.expected_streams(), found_catalog_names)
        print("discovered schemas are OK")

        return found_catalogs

    def run_and_verify_sync(self, conn_id):
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
            self, conn_id, self.expected_streams(), self.expected_primary_keys())

        return sync_record_count


    def min_bookmarks_by_stream(self, sync_records):
        """Return the minimum value for the replication key for each stream"""
        min_bookmarks = {}
        for stream, batch in sync_records.items():

            upsert_messages = [m for m in batch.get('messages') if m['action'] == 'upsert']
            stream_bookmark_key = self.expected_replication_keys().get(stream, set())
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
            stream_bookmark_key = self.expected_replication_keys().get(stream, set())

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
