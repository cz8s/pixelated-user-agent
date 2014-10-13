#
# Copyright (c) 2014 ThoughtWorks, Inc.
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

import unittest
import json
import sys

import pixelated.user_agent
from pixelated.adapter.tag import Tag
from pixelated.adapter.tag_service import TagService
from mockito import *
import crochet
import pixelated.reactor_manager as reactor_manager
import test.support.test_helper as test_helper
import pixelated.adapter.pixelated_mail
import os


class UserAgentTest(unittest.TestCase):

    def setUp(self):
        self.app = pixelated.user_agent.app.test_client()
        self.mail_service = mock()
        self.tag_service = mock()
        self.draft_service = mock()
        self.search_engine = mock()

        pixelated.user_agent.DISABLED_FEATURES = []
        pixelated.user_agent.mail_service = self.mail_service
        pixelated.user_agent.tag_service = self.tag_service
        pixelated.user_agent.draft_service = self.draft_service
        pixelated.user_agent.search_engine = self.search_engine
        self.input_mail = None
        pixelated.adapter.pixelated_mail.input_mail_from_dict = lambda x: self.input_mail

    def tearDown(self):
        unstub()

    def test_sending_mail_return_sent_mail_data_when_send_succeeds(self):
        self.input_mail = test_helper.input_mail()
        when(self.mail_service).send(1, self.input_mail).thenReturn(self.input_mail)
        self.input_mail.as_dict = lambda: {'header': {'from': 'a@a.a', 'to': 'b@b.b'},
                                           'ident': 1,
                                           'tags': [],
                                           'status': [],
                                           'security_casing': {},
                                           'body': 'email body'}

        result = self.app.post('/mails', data='{"ident":1}', content_type="application/json")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, '{"status": [], "body": "email body", "ident": 1, "tags": [], "header": {"to": "b@b.b", "from": "a@a.a"}, "security_casing": {}}')

    def test_sending_mail_return_error_message_when_send_fails(self):
        self.input_mail = test_helper.input_mail()

        def send_that_throws_exception(id, mail):
            raise Exception('email sending failed', 'more information of error')

        self.mail_service.send = send_that_throws_exception

        result = self.app.post('/mails', data='{"ident":1}', content_type="application/json")

        self.assertEqual(result.status_code, 500)
        self.assertEqual(result.data, '{"message": "email sending failed\\nmore information of error"}')

    def test_that_default_config_file_is_home_dot_pixelated(self):
        orig_config = pixelated.user_agent.app.config
        try:
            when(crochet).setup().thenReturn(None)
            when(reactor_manager).start_reactor().thenReturn(None)
            when(pixelated.user_agent).start_user_agent().thenReturn(None)
            pixelated.user_agent.app.config = mock()

            sys.argv = ['/tmp/does_not_exist']
            pixelated.user_agent.setup()

            verify(pixelated.user_agent.app.config).from_pyfile(os.path.join(os.environ['HOME'], '.pixelated'))
        finally:
            pixelated.user_agent.app.config = orig_config

    def test_that_config_file_can_be_specified_on_command_line(self):
        orig_config = pixelated.user_agent.app.config
        try:
            when(crochet).setup().thenReturn(None)
            when(reactor_manager).start_reactor().thenReturn(None)
            when(pixelated.user_agent).start_user_agent().thenReturn(None)
            pixelated.user_agent.app.config = mock()

            sys.argv = ['/tmp/does_not_exist', '--config', '/tmp/some/config/file']
            pixelated.user_agent.setup()

            verify(pixelated.user_agent.app.config).from_pyfile('/tmp/some/config/file')
        finally:
            pixelated.user_agent.app.config = orig_config