
# tap-recurly

Tap for [Recurly](https://recurly.com/).

## Requirements

- pip3
- python 3.5+
- mkvirtualenv

## Installation

In the directory:

```
$ mkvirtualenv -p python3 tap-recurly
$ pip3 install -e .
```

## Usage

### Create config file

This config is to authenticate into Recurly. The `quota_limit` is the percentage of the rate limit dedicated to the tap.

```
{
  "start_date" : "2017-01-01T00:00:00Z",
  "user_agent" : "stitch(+support@stitchdata.com)",
  "subdomain": "lambtron",
  "api_key": "99xxxx",
  "quota_limit": 50
}
```

### Discovery mode

This command returns a JSON that describes the schema of each table.

```
$ tap-recurly --config config.json --discover
```

To save this to `catalog.json`:

```
$ tap-recurly --config config.json --discover > catalog.json
```

### Field selection

You can tell the tap to extract specific fields by editing `catalog.json` to make selections. Note the top-level `selected` attribute, as well as the `selected` attribute nested under each property.

```
{
  "selected": "true",
  "properties": {
    "likes_getting_petted": {
      "selected": "true",
      "inclusion": "available",
      "type": [
        "null",
        "boolean"
      ]
    },
    "name": {
      "selected": "true",
      "maxLength": 255,
      "inclusion": "available",
      "type": [
        "null",
        "string"
      ]
    },
    "id": {
      "selected": "true",
      "minimum": -2147483648,
      "inclusion": "automatic",
      "maximum": 2147483647,
      "type": [
        "null",
        "integer"
      ]
    }
  },
  "type": "object"
}
```

### Sync Mode

With an annotated `catalog.json`, the tap can be invoked in sync mode:

```
$ tap-recurly --config config.json --catalog catalog.json
```

Messages are written to standard output following the Singer specification. The resultant stream of JSON data can be consumed by a Singer target.


## Replication Methods and State File

### Incremental

- Accounts
- Accounts Coupon Redemptions
- Adjustments
- Billing Info
- Coupons
- Invoices
- Invoices Coupon Redemptions
- Plans
- Plans Add Ons
- Subscriptions
- Transactions
- Usages

### Full Table

None.

Copyright &copy; 2019 Stitch
