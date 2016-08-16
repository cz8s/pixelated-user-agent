#
# Copyright (c) 2016 ThoughtWorks, Inc.
#
# Pixelated is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Pixelated is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Pixelated. If not, see <http://www.gnu.org/licenses/>.

import logging
import os
from xml.sax import SAXParseException

from twisted.cred import credentials
from twisted.internet import defer
from twisted.python.filepath import FilePath
from twisted.web import util
from twisted.web.http import UNAUTHORIZED, OK
from twisted.web.resource import IResource, NoResource
from twisted.web.server import NOT_DONE_YET
from twisted.web.static import File
from twisted.web.template import Element, XMLFile, renderElement, renderer
from pixelated.resources import handle_error_deferred
from pixelated.adapter.welcome_mail import add_welcome_mail
from pixelated.resources import BaseResource, UnAuthorizedResource, IPixelatedSession
from pixelated.support.clock import Clock
import datetime

log = logging.getLogger(__name__)


def _get_startup_folder():
    path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(path, '..', 'assets')


def _get_static_folder():
    static_folder = os.path.abspath(os.path.join(os.path.abspath(__file__), "..", "..", "..", "web-ui", "app"))
    # this is a workaround for packaging
    if not os.path.exists(static_folder):
        static_folder = os.path.abspath(
            os.path.join(os.path.abspath(__file__), "..", "..", "..", "..", "web-ui", "app"))
    if not os.path.exists(static_folder):
        static_folder = os.path.join('/', 'usr', 'share', 'pixelated-user-agent')
    return static_folder


class DisclaimerElement(Element):
    loader = XMLFile(FilePath(os.path.join(_get_startup_folder(), '_login_disclaimer_banner.html')))

    def __init__(self, banner):
        super(DisclaimerElement, self).__init__()
        self._set_loader(banner)
        self._banner_filename = banner or "_login_disclaimer_banner.html"

    def _set_loader(self, banner):
        if banner:
            current_path = os.path.dirname(os.path.abspath(__file__))
            banner_file_path = os.path.join(current_path, "..", "..", "..", banner)
            self.loader = XMLFile(FilePath(banner_file_path))

    def render(self, request):
        try:
            return super(DisclaimerElement, self).render(request)
        except SAXParseException:
            return ["Invalid XML template format for %s." % self._banner_filename]
        except IOError:
            return ["Disclaimer banner file %s could not be read or does not exit." % self._banner_filename]


class LoginWebSite(Element):
    loader = XMLFile(FilePath(os.path.join(_get_startup_folder(), 'login.html')))

    def __init__(self, error_msg=None, disclaimer_banner_file=None):
        super(LoginWebSite, self).__init__()
        self._error_msg = error_msg
        self.disclaimer_banner_file = disclaimer_banner_file

    @renderer
    def error_msg(self, request, tag):
        if self._error_msg is not None:
            return tag(self._error_msg)
        return tag('')

    @renderer
    def disclaimer(self, request, tag):
        return DisclaimerElement(self.disclaimer_banner_file).render(request)


class LoginResource(BaseResource):
    BASE_URL = 'login'

    def __init__(self, services_factory, portal=None, disclaimer_banner=None):
        BaseResource.__init__(self, services_factory)
        self._static_folder = _get_static_folder()
        self._startup_folder = _get_startup_folder()
        self._portal = portal
        self._disclaimer_banner = disclaimer_banner
        self.putChild('startup-assets', File(self._startup_folder))

    def set_portal(self, portal):
        self._portal = portal

    def getChild(self, path, request):
        if path == '':
            return self
        if path == 'login':
            return self
        if not self.is_logged_in(request):
            return UnAuthorizedResource()
        return NoResource()

    def render_GET(self, request):
        request.setResponseCode(OK)
        return self._render_template(request)

    def _render_template(self, request, error_msg=None):
        site = LoginWebSite(error_msg=error_msg, disclaimer_banner_file=self._disclaimer_banner)
        return renderElement(request, site)

    def render_POST(self, request):
        before = datetime.datetime.now()
        tl = Clock('naval login user: %s' % request.args['username'][0])
        if self.is_logged_in(request):
            log.info('naval already logged in %s' % request.args['username'][0])
            return util.redirectTo("/", request)

        def render_response(leap_session):
            request.setResponseCode(OK)
            t = Clock('login-reading-interstitial', leap_session.user_auth.uuid)
            request.write(open(os.path.join(self._startup_folder, 'Interstitial.html')).read())
            t.stop(leap_session.fresh_account)
            tl.stop()
            request.finish()
            #import pdb; pdb.set_trace()
            self._setup_user_services(leap_session, request)

        def render_error(error):
            log.info('Login Error for %s' % request.args['username'][0])
            log.info('%s' % error)
            request.setResponseCode(UNAUTHORIZED)
            return self._render_template(request, 'Invalid credentials')

        d = self._handle_login(request)
        d.addCallbacks(render_response, render_error)
        d.addErrback(handle_error_deferred, request)

        return NOT_DONE_YET

    @defer.inlineCallbacks
    def _handle_login(self, request):
        self.creds = self._get_creds_from(request)
        t = Clock('login-leap-session')
        iface, leap_session, logout = yield self._portal.login(self.creds, None, IResource)
        t.stop(leap_session.fresh_account, leap_session.user_auth.uuid)
        defer.returnValue(leap_session)

    def _get_creds_from(self, request):
        username = request.args['username'][0]
        password = request.args['password'][0]
        return credentials.UsernamePassword(username, password)

    @defer.inlineCallbacks
    def _setup_user_services(self, leap_session, request):
        user_id = leap_session.user_auth.uuid
        t = Clock('login-setup-services', user_id)
        if not self._services_factory.has_session(user_id):
            yield self._services_factory.create_services_from(leap_session)
            self._services_factory.map_email(self.creds.username, user_id)

        if leap_session.fresh_account:
            yield add_welcome_mail(leap_session.mail_store)

        self._init_http_session(request, user_id)
        t.stop(leap_session.fresh_account)


    def _init_http_session(self, request, user_id):
        session = IPixelatedSession(request.getSession())
        session.user_uuid = user_id
