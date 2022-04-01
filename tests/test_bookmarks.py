import os
import re
from datetime import datetime as dt
from datetime import timedelta

from tap_tester import menagerie, connections, runner

from base import RecurlyBaseTest


class BookmarksTest(RecurlyBaseTest):
    """Test tap bookmarks."""

    @staticmethod
    def name():
        return "tt_recurly_bookmarks"

    def assertIsDateFormat(self, value, str_format):
        """
        Assertion Method that verifies a string value is a formatted datetime with
        the specified format.
        """
        try:
            _ = dt.strptime(value, str_format)
        except ValueError as err:
            raise AssertionError(
                f"Value does not conform to expected format: {str_format}"
            ) from err


    def test_run(self):
        """
        Testing that the tap sets state based on max replication key value for an
        incremental stream, and that it syncs inlcusively on the preious state.

        NOTE: Bookmark and Replication Keys  have slightly differnt dt formats.
              Bookmark does not have fractional seconds, rep keys do (but always .000000 ?).

              The coupons stream is not under test.

        """
        print("Bookmarks Test for tap-recurly")

        conn_id = connections.ensure_connection(self)

        streams_under_test = self.expected_streams() - {
            'coupon_redemptions',  # does not save bookmarks - different key ?
            'coupons',  # does not save bookmarks - no data was returned
            'plans_add_ons',  # does not save bookmarks - child stream ?
            'billing_info',  # BUG - saves bookmarks but does not pick back up from that bookmark
        }

        # Run a discovery job
        found_catalogs_1 = self.run_and_verify_check_mode(conn_id)

        # partition catalogs for use in table/field seelction
        test_catalogs_1 = [catalog for catalog in found_catalogs_1
                           if catalog.get('stream_name') in streams_under_test]

        # select all fields for core streams
        self.select_all_streams_and_fields(conn_id, test_catalogs_1, select_all_fields=True)

        # Run a sync
        _ = self.run_and_verify_sync(conn_id)

        # acquire records from target output
        synced_records_1 = runner.get_records_from_target_output()
        state_1 = menagerie.get_state(conn_id)
        bookmarks_1 = state_1.get('bookmarks')
        currently_syncing_1 = state_1.get('currently_syncing')

        # inject a simulated state value for each stream under test
        injected_state_by_stream = dict()
        for stream in streams_under_test:
            replication_key = list(self.expected_replication_keys()[stream])[0]  # assumes no compound keys
            state_1_bookmark_datetime = dt.strptime(
                state_1['bookmarks'][stream][replication_key], self.BOOKMARK_KEY_FORMAT
            )
            new_state = dt.strftime(
                state_1_bookmark_datetime - timedelta(days=7), self.BOOKMARK_KEY_FORMAT
            )
            injected_state_by_stream[stream] = {replication_key: new_state}
        manipulated_state = {'bookmarks': injected_state_by_stream}
        menagerie.set_state(conn_id, manipulated_state)

        # Run another sync with the manipulated state
        _ = self.run_and_verify_sync(conn_id)

        # acquire records from target output
        synced_records_2 = runner.get_records_from_target_output()
        state_2 = menagerie.get_state(conn_id)
        bookmarks_2 = state_2.get('bookmarks')
        currently_syncing_2 = state_2.get('currently_syncing')

        # Run another sync without manipulating state
        _ = self.run_and_verify_sync(conn_id)

        # acquire records from target output
        synced_records_3 = runner.get_records_from_target_output()
        state_3 = menagerie.get_state(conn_id)
        bookmarks_3 = state_3.get('bookmarks')
        currently_syncing_3 = state_3.get('currently_syncing')

        # Checking syncs were successful prior to stream-level assertions
        with self.subTest():

            # Verify sync completed by checking currently_syncing in state for sync 1
            self.assertIsNone(currently_syncing_1)
            # Verify bookmarks are saved
            self.assertIsNotNone(bookmarks_1)

            # Verify sync completed by checking currently_syncing in state for sync 2
            self.assertIsNone(currently_syncing_2)
            # Verify bookmarks are saved
            self.assertIsNotNone(bookmarks_2)

            # Verify sync completed by checking currently_syncing in state for sync 3
            self.assertIsNone(currently_syncing_3)
            # Verify bookmarks are saved
            self.assertIsNotNone(bookmarks_3)

            # Verify bookmarks saved match across syncs
            # (assumes no changes to test data during test execution)
            self.assertEqual(bookmarks_1, bookmarks_2)
            self.assertEqual(bookmarks_2, bookmarks_3)

        # stream-level assertions
        for stream in streams_under_test:
            with self.subTest(stream=stream):

                # set expectations
                expected_replication_method = self.expected_replication_method()[stream]
                expected_replication_key = list(self.expected_replication_keys()[stream])[0]
                expected_primary_key = list(self.expected_primary_keys()[stream])[0]  # assumes 1 value

                # gather results
                records_1 = [message['data'] for message in synced_records_1[stream]['messages']]
                records_2 = [message['data'] for message in synced_records_2[stream]['messages']]
                records_3 = [message['data'] for message in synced_records_3[stream]['messages']]
                record_count_1 = len(records_1)
                record_count_2 = len(records_2)
                record_count_3 = len(records_3)

                replication_key_values_1 = [record.get(expected_replication_key) for record in records_1]
                replication_key_values_2 = [record.get(expected_replication_key) for record in records_2]
                replication_key_values_3 = [record.get(expected_replication_key) for record in records_3]

                primary_key_values_1 = [record.get(expected_primary_key) for record in records_1]
                primary_key_values_2 = [record.get(expected_primary_key) for record in records_2]
                primary_key_values_3 = [record.get(expected_primary_key) for record in records_3]

                stream_bookmark_1 = bookmarks_1.get(stream)
                stream_bookmark_2 = bookmarks_2.get(stream)
                stream_bookmark_3 = bookmarks_3.get(stream)

                manipulated_bookmark = manipulated_state['bookmarks'][stream]
                parsed_manipulated_state = dt.strptime(
                    manipulated_bookmark.get(expected_replication_key),
                    self.BOOKMARK_KEY_FORMAT
                )
                parsed_bookmark_3 = dt.strptime(
                    stream_bookmark_3.get(expected_replication_key),
                    self.BOOKMARK_KEY_FORMAT
                )

                # for each sync...
                for index, sync_results in enumerate([(stream_bookmark_1, replication_key_values_1),
                                                           (stream_bookmark_2, replication_key_values_2),
                                                           (stream_bookmark_3, replication_key_values_3),]):

                    stream_bookmark, replication_key_values = sync_results

                    with self.subTest(sync=f"Sync {index + 1}"):

                        # Verify bookmarks saved match formatting standards
                        self.assertIsNotNone(stream_bookmark)
                        bookmark_value = stream_bookmark.get(expected_replication_key)
                        self.assertIsNotNone(bookmark_value)
                        self.assertIsInstance(bookmark_value, str)
                        self.assertIsDateFormat(bookmark_value, self.BOOKMARK_KEY_FORMAT)

                        # Verify records are replicated in ascending order of replication key value
                        self.assertEqual(replication_key_values, sorted(replication_key_values))

                        # Verify the bookmark is set based on max replication key value
                        max_replication_key_value = dt.strptime(replication_key_values[-1], self.REPLICATION_KEY_FORMAT)
                        parsed_bookmaark_value = dt.strptime(bookmark_value, self.BOOKMARK_KEY_FORMAT)
                        self.assertEqual(parsed_bookmaark_value, max_replication_key_value)


                # Verify 2nd sync only replicates records from manipulated state onward
                for replication_key_value in replication_key_values_2:
                    parsed_replication_key_value = dt.strptime(replication_key_value, self.REPLICATION_KEY_FORMAT)
                    self.assertGreaterEqual(parsed_replication_key_value, parsed_manipulated_state)

                # Verify records in the 1st sync with replication key values >= parsed_manipulated_state
                # are replicated in the 2nd sync
                expected_records = {primary_key_value: replication_key_value
                                    for primary_key_value, replication_key_value
                                    in zip(primary_key_values_1, replication_key_values_1)
                                    if dt.strptime(replication_key_value, self.REPLICATION_KEY_FORMAT) >= parsed_manipulated_state}
                actual_records = {primary_key_value: replication_key_value
                                  for primary_key_value, replication_key_value
                                  in zip(primary_key_values_2, replication_key_values_2)}
                self.assertEqual(expected_records, actual_records)

                # Verify records in the 2nd sync with replication key values = saved state
                # are replicated in the 3rd sync
                expected_records = {primary_key_value: replication_key_value
                                    for primary_key_value, replication_key_value in zip(primary_key_values_2, replication_key_values_2) if
                                    dt.strptime(replication_key_value, self.REPLICATION_KEY_FORMAT) >= parsed_bookmark_3}
                actual_records = {primary_key_value: replication_key_value
                                  for primary_key_value, replication_key_value in zip(primary_key_values_3, replication_key_values_3)}
                self.assertEqual(expected_records, actual_records)

                # Verify at least 1 record was replicated for each stream (sanity/inclusivity check)
                self.assertGreater(record_count_1, 0)
                self.assertGreater(record_count_2, 0)
                self.assertGreater(record_count_3, 0)

                print(f"Sync 1:  {record_count_1} {stream} records replicated")
                print(f"Sync 2:  {record_count_2} {stream} records replicated")
                print(f"Sync 3:  {record_count_3} {stream} records replicated")
