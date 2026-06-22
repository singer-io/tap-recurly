import unittest
from unittest.mock import patch, MagicMock
import requests

from tap_recurly.streams import (
    Stream, Accounts, BillingInfo, Adjustments, CouponRedemptions,
    Coupons, Invoices, Plans, PlansAddOns, Subscriptions, Transactions, STREAMS
)
from tap_recurly.discover import discover_streams, _apply_access_checks, _prune_inaccessible_children
from tap_recurly.exceptions import RecurlyForbiddenError


def _make_client():
    client = MagicMock()
    client.site_id = "subdomain-test"
    return client


def _make_streams_data(stream_names=None):
    if stream_names is None:
        stream_names = list(STREAMS.keys())
    return {name: {"stream": name, "tap_stream_id": name} for name in stream_names}


def _make_403_error():
    return RecurlyForbiddenError("403 Forbidden")


# ---------------------------------------------------------------------------
# check_access() on individual Stream classes
# ---------------------------------------------------------------------------
class TestCheckAccess(unittest.TestCase):

    def test_child_stream_billing_info_returns_true(self):
        """BillingInfo has parent='accounts' and should skip the API call."""
        client = _make_client()
        self.assertTrue(BillingInfo(client=client).check_access())
        client._get.assert_not_called()

    def test_child_stream_plans_add_ons_returns_true(self):
        """PlansAddOns has parent='plans' and should skip the API call."""
        client = _make_client()
        self.assertTrue(PlansAddOns(client=client).check_access())
        client._get.assert_not_called()

    def test_multi_parent_coupon_redemptions_returns_true(self):
        """CouponRedemptions has parent_streams and should skip the API call."""
        client = _make_client()
        self.assertTrue(CouponRedemptions(client=client).check_access())
        client._get.assert_not_called()

    def test_accessible_parent_stream_returns_true(self):
        """Accounts is accessible — check_access should return True."""
        client = _make_client()
        client._get.return_value = {"data": [], "has_more": False}
        self.assertTrue(Accounts(client=client).check_access())
        client._get.assert_called_once_with("sites/subdomain-test/accounts?limit=1")

    def test_forbidden_parent_stream_returns_false(self):
        """Accounts returns 403 — check_access should return False."""
        client = _make_client()
        client._get.side_effect = _make_403_error()
        self.assertFalse(Accounts(client=client).check_access())

    @patch('tap_recurly.streams.LOGGER')
    def test_forbidden_stream_logs_unauthorized_warning(self, mock_logger):
        """Verify the 'Unauthorized Stream' warning is logged with stream name and error."""
        client = _make_client()
        error = _make_403_error()
        client._get.side_effect = error
        Accounts(client=client).check_access()
        mock_logger.warning.assert_called_once_with(
            "Unauthorized Stream: %s, excluding from catalog. HTTP-Error-Message:'%s'",
            "accounts",
            error,
        )

    def test_non_403_error_is_reraised(self):
        """A 500 error should propagate, not be swallowed."""
        client = _make_client()
        resp = MagicMock()
        resp.status_code = 500
        client._get.side_effect = requests.exceptions.HTTPError(response=resp)
        with self.assertRaises(requests.exceptions.HTTPError):
            Accounts(client=client).check_access()

    def test_adjustments_uses_api_resource_line_items(self):
        """Adjustments.api_resource maps to 'line_items' in the URL."""
        client = _make_client()
        client._get.return_value = {"data": [], "has_more": False}
        Adjustments(client=client).check_access()
        client._get.assert_called_once_with("sites/subdomain-test/line_items?limit=1")

    def test_all_parent_streams_hit_correct_endpoints(self):
        """Verify every non-child stream builds the right path."""
        client = _make_client()
        client._get.return_value = {"data": [], "has_more": False}
        expected = {
            "accounts": "sites/subdomain-test/accounts?limit=1",
            "adjustments": "sites/subdomain-test/line_items?limit=1",
            "coupons": "sites/subdomain-test/coupons?limit=1",
            "invoices": "sites/subdomain-test/invoices?limit=1",
            "plans": "sites/subdomain-test/plans?limit=1",
            "subscriptions": "sites/subdomain-test/subscriptions?limit=1",
            "transactions": "sites/subdomain-test/transactions?limit=1",
        }
        for name, path in expected.items():
            client.reset_mock()
            STREAMS[name](client=client).check_access()
            client._get.assert_called_once_with(path)


# ---------------------------------------------------------------------------
# _apply_access_checks()
# ---------------------------------------------------------------------------
class TestApplyAccessChecks(unittest.TestCase):

    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'billing_info': BillingInfo,
        'coupons': Coupons,
    })
    def test_all_accessible(self):
        client = _make_client()
        client._get.return_value = {"data": [], "has_more": False}
        streams_data = _make_streams_data(['accounts', 'billing_info', 'coupons'])

        _apply_access_checks(client, streams_data)

        self.assertIn('accounts', streams_data)
        self.assertIn('billing_info', streams_data)
        self.assertIn('coupons', streams_data)

    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'billing_info': BillingInfo,
        'coupons': Coupons,
    })
    def test_partial_access_excludes_forbidden_and_children(self):
        """accounts is forbidden → accounts AND billing_info (child) removed."""
        client = _make_client()

        def side_effect(path):
            if 'accounts' in path:
                raise _make_403_error()
            return {"data": [], "has_more": False}

        client._get.side_effect = side_effect
        streams_data = _make_streams_data(['accounts', 'billing_info', 'coupons'])

        _apply_access_checks(client, streams_data)

        self.assertNotIn('accounts', streams_data)
        self.assertNotIn('billing_info', streams_data)
        self.assertIn('coupons', streams_data)

    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'coupons': Coupons,
    })
    def test_no_accessible_streams_raises(self):
        client = _make_client()
        client._get.side_effect = _make_403_error()
        streams_data = _make_streams_data(['accounts', 'coupons'])

        with self.assertRaises(RecurlyForbiddenError):
            _apply_access_checks(client, streams_data)

    @patch('tap_recurly.discover.STREAMS', {
        'plans': Plans,
        'plans_add_ons': PlansAddOns,
        'coupons': Coupons,
    })
    def test_plans_forbidden_prunes_plans_add_ons(self):
        """plans is forbidden -> plans_add_ons (child) is also removed."""
        client = _make_client()

        def side_effect(path):
            if 'plans' in path:
                raise _make_403_error()
            return {"data": [], "has_more": False}

        client._get.side_effect = side_effect
        streams_data = _make_streams_data(['plans', 'plans_add_ons', 'coupons'])

        _apply_access_checks(client, streams_data)

        self.assertNotIn('plans', streams_data)
        self.assertNotIn('plans_add_ons', streams_data)
        self.assertIn('coupons', streams_data)


# ---------------------------------------------------------------------------
# _prune_inaccessible_children()
# ---------------------------------------------------------------------------
class TestPruneInaccessibleChildren(unittest.TestCase):

    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'billing_info': BillingInfo,
    })
    def test_child_pruned_when_parent_missing(self):
        streams_data = _make_streams_data(['billing_info'])
        _prune_inaccessible_children(streams_data)
        self.assertNotIn('billing_info', streams_data)

    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'billing_info': BillingInfo,
    })
    def test_child_kept_when_parent_present(self):
        streams_data = _make_streams_data(['accounts', 'billing_info'])
        _prune_inaccessible_children(streams_data)
        self.assertIn('billing_info', streams_data)

    @patch('tap_recurly.discover.STREAMS', {
        'plans': Plans,
        'plans_add_ons': PlansAddOns,
    })
    def test_plans_add_ons_pruned_when_plans_missing(self):
        """PlansAddOns has parent='plans', so it is pruned when plans is missing."""
        streams_data = _make_streams_data(['plans_add_ons'])
        _prune_inaccessible_children(streams_data)
        self.assertNotIn('plans_add_ons', streams_data)

    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'subscriptions': Subscriptions,
        'invoices': Invoices,
        'coupon_redemptions': CouponRedemptions,
    })
    def test_coupon_redemptions_pruned_when_all_parents_missing(self):
        streams_data = _make_streams_data(['coupon_redemptions'])
        _prune_inaccessible_children(streams_data)
        self.assertNotIn('coupon_redemptions', streams_data)

    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'subscriptions': Subscriptions,
        'invoices': Invoices,
        'coupon_redemptions': CouponRedemptions,
    })
    def test_coupon_redemptions_kept_when_one_parent_present(self):
        streams_data = _make_streams_data(['accounts', 'coupon_redemptions'])
        _prune_inaccessible_children(streams_data)
        self.assertIn('coupon_redemptions', streams_data)


# ---------------------------------------------------------------------------
# discover_streams() — integration-level
# ---------------------------------------------------------------------------
class TestDiscoverStreams(unittest.TestCase):

    @patch('tap_recurly.discover._apply_access_checks')
    def test_returns_list_with_required_keys(self, mock_access_checks):
        client = _make_client()
        mock_access_checks.return_value = None

        result = discover_streams(client)

        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)
        for entry in result:
            self.assertIn('stream', entry)
            self.assertIn('tap_stream_id', entry)
            self.assertIn('schema', entry)
            self.assertIn('metadata', entry)

    @patch('tap_recurly.discover._apply_access_checks')
    def test_all_streams_present_when_all_accessible(self, mock_access_checks):
        client = _make_client()
        mock_access_checks.return_value = None

        result = discover_streams(client)
        discovered = {s['tap_stream_id'] for s in result}

        for stream_name in STREAMS:
            self.assertIn(stream_name, discovered)


# ---------------------------------------------------------------------------
# Warning / error message content
# ---------------------------------------------------------------------------
class TestLogMessages(unittest.TestCase):

    @patch('tap_recurly.discover.LOGGER')
    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'coupons': Coupons,
    })
    def test_partial_access_logs_excluded_streams(self, mock_logger):
        """Verify the 403 exclusion warning message is emitted."""
        client = _make_client()

        def side_effect(path):
            if 'accounts' in path:
                raise _make_403_error()
            return {"data": [], "has_more": False}

        client._get.side_effect = side_effect
        streams_data = _make_streams_data(['accounts', 'coupons'])

        _apply_access_checks(client, streams_data)

        mock_logger.warning.assert_any_call(
            "These streams have been excluded due to HTTP-Error-Code:403 Forbidden: %s",
            "accounts",
        )

    @patch('tap_recurly.discover.LOGGER')
    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'billing_info': BillingInfo,
        'coupons': Coupons,
    })
    def test_child_exclusion_logs_parent_reason(self, mock_logger):
        """Verify the child-pruned warning references the parent stream."""
        client = _make_client()

        def side_effect(path):
            if 'accounts' in path:
                raise _make_403_error()
            return {"data": [], "has_more": False}

        client._get.side_effect = side_effect
        streams_data = _make_streams_data(['accounts', 'billing_info', 'coupons'])

        _apply_access_checks(client, streams_data)

        mock_logger.warning.assert_any_call(
            "Stream '%s' excluded because its parent "
            "stream '%s' is not accessible.",
            "billing_info", "accounts",
        )

    @patch('tap_recurly.discover.LOGGER')
    @patch('tap_recurly.discover.STREAMS', {
        'accounts': Accounts,
        'subscriptions': Subscriptions,
        'invoices': Invoices,
        'coupon_redemptions': CouponRedemptions,
    })
    def test_all_streams_forbidden_raises_error(self, mock_logger):
        """When all streams return 403, RecurlyForbiddenError is raised."""
        client = _make_client()
        client._get.side_effect = _make_403_error()
        streams_data = _make_streams_data(['accounts', 'subscriptions', 'invoices', 'coupon_redemptions'])

        with self.assertRaises(RecurlyForbiddenError):
            _apply_access_checks(client, streams_data)

    def test_no_access_error_message_content(self):
        """Verify RecurlyForbiddenError message text."""
        client = _make_client()
        client._get.side_effect = _make_403_error()
        streams_data = _make_streams_data(['accounts'])

        with self.assertRaises(RecurlyForbiddenError) as ctx:
            with patch('tap_recurly.discover.STREAMS', {'accounts': Accounts}):
                _apply_access_checks(client, streams_data)

        self.assertIn("No streams are accessible", str(ctx.exception))
        self.assertIn("read permission", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
