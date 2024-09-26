#
# Module dependencies.
#

from urllib import parse
import logging
import time
import backoff
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger()

def retry_handler(details):
    logger.info("Received 429 -- sleeping for %s seconds",
                details['wait'])


class Recurly():
    """ Simple wrapper for Recurly. """

    def __init__(self, subdomain, api_key, start_date=None, user_agent=None, quota_limit=100):
        self.headers = {'Accept': 'application/vnd.recurly.v2021-02-25'}
        self.site_id = "subdomain-{subdomain}".format(subdomain=subdomain)
        self.user_agent = user_agent
        self.start_date = start_date
        self.limit = 200
        self.api_key = api_key
        self.uri = "https://partner-api.recurly.com/"
        self.quota_limit = int(quota_limit)


    def sleep_until(self, timestamp):
        difference_in_seconds = int(timestamp) - time.time()
        logger.info("Sleeping %s seconds until %s", difference_in_seconds, timestamp)
        logger.info("Quota Rate Limit (tap's permitted usage %% of the API): %s", self.quota_limit)
        time.sleep(difference_in_seconds)


    def check_rate_limit(self, limit_remaining, limit_limit, limit_reset_time):
        if 100 - (100 * int(limit_remaining) / int(limit_limit)) >= self.quota_limit:
            logger.info("Quota Remaining / Quota Total: %s / %s", limit_remaining, limit_limit)
            self.sleep_until(limit_reset_time)


    @backoff.on_exception(backoff.expo,
                          requests.exceptions.RetryError,
                          on_backoff=retry_handler,
                          max_tries=5)
    def _get(self, path):
        uri = "{uri}{path}".format(uri=self.uri, path=path)
        logger.info("GET request to %s", uri)
        response = requests.get(uri, headers=self.headers, auth=HTTPBasicAuth(self.api_key, ''))
        response.raise_for_status()

        limit_remaining = response.headers.get('X-RateLimit-Remaining')
        limit_limit = response.headers.get('X-RateLimit-Limit')
        limit_reset_time = response.headers.get('X-RateLimit-Reset')
        self.check_rate_limit(limit_remaining, limit_limit, limit_reset_time)
        return response.json()


    def _get_all(self, path):
        has_more = True
        while has_more:
            try:
                json = self._get(path)
                has_more = json["has_more"]
                path = json["next"]
                data = json["data"]
                for item in data:
                    yield item
            except requests.exceptions.HTTPError as err:
                logger.info("Response returned http error code %s", err.response.status_code)

                if err.response.status_code == 401:
                    logger.critical("Response returned http error code 401")
                    raise

                if err.response.status_code == 404:
                    break

            except KeyError:
                yield json
                break

    #
    # Methods to retrieve data per stream/resource.
    #

    def accounts(self, column_name, bookmark):
        url = "sites/{site_id}/accounts"
        url += "?limit={limit}&sort={column_name}&begin_time={bookmark}&order=asc"
        url = url.format(site_id=self.site_id,
                         limit=self.limit,
                         column_name=column_name,
                         bookmark=parse.quote(bookmark))
        return self._get_all(url)

    # substream of accounts
    def billing_info(self, account_id, column_name):
        url = "sites/{site_id}/accounts/{account_id}/billing_info"
        url += "?limit={limit}&sort={column_name}&order=asc"
        url = url.format(site_id=self.site_id,
                         account_id=account_id,
                         limit=self.limit,
                         column_name=column_name)
        for item in self._get_all(url):
            yield item

    def adjustments(self, column_name, bookmark):
        url = "sites/{site_id}/line_items"
        url += "?limit={limit}&sort={column_name}&begin_time={bookmark}&order=asc"
        url = url.format(site_id=self.site_id,
                         limit=self.limit,
                         column_name=column_name,
                         bookmark=parse.quote(bookmark))
        return self._get_all(url)

    def accounts_coupon_redemptions(self, account_id, column_name):
        url = "sites/{site_id}/accounts/{account_id}/coupon_redemptions"
        url += "?limit={limit}&sort={column_name}&order=asc"
        url = url.format(site_id=self.site_id,
                         account_id=account_id,
                         limit=self.limit,
                         column_name=column_name)
        for item in self._get_all(url):
            yield item

    def invoices_coupon_redemptions(self, invoice_id, column_name):
        url = "sites/{site_id}/invoices/{invoice_id}/coupon_redemptions"
        url += "?limit={limit}&sort={column_name}&order=asc"
        url = url.format(site_id=self.site_id,
                         invoice_id=invoice_id,
                         limit=self.limit,
                         column_name=column_name)
        for item in self._get_all(url):
            yield item

    def subscriptions_coupon_redemptions(self, subscription_id, column_name):
        url = "sites/{site_id}/subscriptions/{subscription_id}/coupon_redemptions"
        url += "?limit={limit}&sort={column_name}&order=asc"
        url = url.format(site_id=self.site_id,
                         subscription_id=subscription_id,
                         limit=self.limit,
                         column_name=column_name)
        for item in self._get_all(url):
            yield item

    def usages(self, subscription_id, add_on_id, column_name):
        url = "sites/{site_id}/subscriptions/{subscription_id}/add_ons/{add_on_id}/usage"
        url += "?billing_status=all&limit={limit}&sort={column_name}&order=asc"
        url = url.format(site_id=self.site_id,
                         subscription_id=subscription_id,
                         add_on_id=add_on_id,
                         limit=self.limit,
                         column_name=column_name)
        for item in self._get_all(url):
            yield item

    def coupons(self, column_name, bookmark):
        url = "sites/{site_id}/coupons"
        url += "?limit={limit}&sort={column_name}&begin_time={bookmark}&order=asc"
        url = url.format(site_id=self.site_id,
                         limit=self.limit,
                         column_name=column_name,
                         bookmark=parse.quote(bookmark))
        return self._get_all(url)

    def invoices(self, column_name, bookmark):
        url = "sites/{site_id}/invoices"
        url += "?limit={limit}&sort={column_name}&begin_time={bookmark}&order=asc"
        url = url.format(site_id=self.site_id,
                         limit=self.limit,
                         column_name=column_name,
                         bookmark=parse.quote(bookmark))
        return self._get_all(url)

    def plans(self, column_name, bookmark):
        url = "sites/{site_id}/plans"
        url += "?limit={limit}&sort={column_name}&begin_time={bookmark}&order=asc"
        url = url.format(site_id=self.site_id,
                         limit=self.limit,
                         column_name=column_name,
                         bookmark=parse.quote(bookmark))
        return self._get_all(url)

    # substream of plans
    def plans_add_ons(self, column_name, bookmark):
        plans = self.plans(column_name, bookmark)
        for plan in plans:
            url = "sites/{site_id}/plans/{plan_id}/add_ons"
            url += "?limit={limit}&sort={column_name}&order=asc"
            url = url.format(site_id=self.site_id,
                             plan_id=plan["id"],
                             limit=self.limit,
                             column_name=column_name)
            for item in self._get_all(url):
                yield item

    def subscriptions(self, column_name, bookmark):
        url = "sites/{site_id}/subscriptions"
        url += "?limit={limit}&sort={column_name}&begin_time={bookmark}&order=asc"
        url = url.format(site_id=self.site_id,
                         limit=self.limit,
                         column_name=column_name,
                         bookmark=parse.quote(bookmark))
        return self._get_all(url)

    def transactions(self, column_name, bookmark):
        column_name = "updated_at"
        url = "sites/{site_id}/transactions"
        url += "?limit={limit}&sort={column_name}&begin_time={bookmark}&order=asc"
        url = url.format(site_id=self.site_id,
                         limit=self.limit,
                         column_name=column_name,
                         bookmark=parse.quote(bookmark))
        return self._get_all(url)
