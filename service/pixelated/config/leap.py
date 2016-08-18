from __future__ import absolute_import
from leap.common.events import (server as events_server)
from leap.soledad.common.errors import InvalidAuthTokenError

from pixelated.config import credentials
from pixelated.bitmask_libraries.config import LeapConfig
from pixelated.bitmask_libraries.certs import LeapCertificate
from pixelated.bitmask_libraries.provider import LeapProvider
from pixelated.bitmask_libraries.session import LeapSessionFactory
from twisted.internet import defer

import logging
log = logging.getLogger(__name__)


def initialize_leap_provider(provider_hostname, provider_cert, provider_fingerprint, leap_home):
    LeapCertificate.set_cert_and_fingerprint(provider_cert,
                                             provider_fingerprint)

    config = LeapConfig(leap_home=leap_home, start_background_jobs=True)
    provider = LeapProvider(provider_hostname, config)
    provider.download_certificate()
    LeapCertificate(provider).setup_ca_bundle()

    return config, provider


@defer.inlineCallbacks
def initialize_leap_multi_user(provider_hostname,
                               leap_provider_cert,
                               leap_provider_cert_fingerprint,
                               credentials_file,
                               leap_home):

    config, provider = initialize_leap_provider(provider_hostname, leap_provider_cert, leap_provider_cert_fingerprint, leap_home)

    defer.returnValue((config, provider))


@defer.inlineCallbacks
def create_leap_session(provider, username, password, initial_sync=True, auth=None):
    leap_session = LeapSessionFactory(provider).create(username, password, auth)
    try:
        if initial_sync:
            yield leap_session.initial_sync()
    except InvalidAuthTokenError:
        try:
            leap_session.close()
        except Exception, e:
            log.error(e)

        leap_session = LeapSessionFactory(provider).create(username, password, auth)
        if initial_sync:
            yield leap_session.initial_sync()

    defer.returnValue(leap_session)


@defer.inlineCallbacks
def initialize_leap_single_user(leap_provider_cert,
                                leap_provider_cert_fingerprint,
                                credentials_file,
                                leap_home,
                                initial_sync=True):

    init_monkeypatches()
    events_server.ensure_server()

    provider, username, password = credentials.read(credentials_file)

    config, provider = initialize_leap_provider(provider, leap_provider_cert, leap_provider_cert_fingerprint, leap_home)

    leap_session = yield create_leap_session(provider, username, password, initial_sync=initial_sync)

    defer.returnValue(leap_session)


def init_monkeypatches():
    import pixelated.extensions.requests_urllib3
