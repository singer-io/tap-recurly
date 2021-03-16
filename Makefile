#
# Default.
#

default: build

#
# Tasks.
#

# Build.
build:
	@pip3 install .

# Dev.
dev:
	@pip3 install -e .

# Deploy.
release:
	@python3 setup.py sdist upload

# Lint.
lint:
	pylint tap_recurly -d missing-docstring,too-few-public-methods,invalid-name,too-many-instance-attributes,too-many-arguments

# Discover.
disc:
	@tap-recurly -c config.json --discover > catalog.json

#
# Phonies.
#

.PHONY: build
.PHONY: dev
.PHONY: release
.PHONY: schema
.PHONY: lint
.PHONY: disc
