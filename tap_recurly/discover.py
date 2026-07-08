#
# Module dependencies.
#

import singer
from tap_recurly import streams
from tap_recurly.streams import STREAMS
from tap_recurly.exceptions import RecurlyForbiddenError


LOGGER = singer.get_logger()


def _apply_access_checks(client, streams_data):
    """
    Probe each stream for read access and remove inaccessible streams
    (and their children) from streams_data in place.
    Note: check_access() always returns True for child streams, so this loop
    effectively identifies only inaccessible parent streams by design.
    Child stream removal is handled separately by _prune_inaccessible_children().
    Raises RecurlyForbiddenError if no parent streams are accessible.
    """
    inaccessible_streams = [
        stream_name
        for stream_name, stream_cls in STREAMS.items()
        if stream_name in streams_data
        and not stream_cls(client=client).check_access()
    ]

    for stream_name in inaccessible_streams:
        streams_data.pop(stream_name, None)

    inaccessible_streams.extend(_prune_inaccessible_children(streams_data))

    if not streams_data:
        raise RecurlyForbiddenError(
            "No streams are accessible. "
            "Ensure the credentials have read permission "
            "for at least one stream."
        )
    if inaccessible_streams:
        LOGGER.warning(
            "Unauthorized streams excluded from catalog: %s",
            ", ".join(inaccessible_streams),
        )


def _prune_inaccessible_children(streams_data):
    """
    Remove child streams from the catalog whose parent stream was excluded.
    Mutates streams_data in place.
    """
    to_remove = []
    for name, stream_cls in list(STREAMS.items()):
        if name not in streams_data:
            continue
        parent = getattr(stream_cls, 'parent', None)
        parent_streams = getattr(stream_cls, 'parent_streams', None)

        if parent and parent not in streams_data:
            LOGGER.warning(
                "Stream '%s' excluded because its parent "
                "stream '%s' is not accessible.",
                name, parent,
            )
            streams_data.pop(name, None)
            to_remove.append(name)
        elif parent_streams and any(
            p not in streams_data for p in parent_streams
        ):
            missing = [p for p in parent_streams if p not in streams_data]
            LOGGER.warning(
                "Stream '%s' excluded because its parent "
                "stream(s) %s are not accessible.",
                name, missing,
            )
            streams_data.pop(name, None)
            to_remove.append(name)
    return to_remove

def discover_streams(client):
    streams_data = {}

    for s in STREAMS.values():
        s = s(client)
        schema = singer.resolve_schema_references(s.load_schema())
        streams_data[s.name] = {'stream': s.name,
                                'tap_stream_id': s.name,
                                'schema': schema,
                                'metadata': s.load_metadata()}

    _apply_access_checks(client, streams_data)

    return list(streams_data.values())
