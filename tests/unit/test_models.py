"""
Contains tests for :mod:`topchef.models`
"""
import pytest
import os
from topchef.models import Service
from topchef import config


class TestService(object):
    service_name = 'TestService'

    @pytest.yield_fixture
    def service(self):
        if not os.path.isdir(config.SCHEMA_DIRECTORY):
            os.mkdir(config.SCHEMA_DIRECTORY)

        service = Service(self.service_name)
        yield service

        service.remove_schema_file()
        if not os.listdir(config.SCHEMA_DIRECTORY):
            os.removedirs(config.SCHEMA_DIRECTORY)

    def test_constructor(self, service):
        assert service.name == self.service_name

    def test_repr(self, service):
        assert service.__repr__() == '%s(id=%d, name=%s)' % (
            service.__class__.__name__, service.id, service.name
        )

    def test_path_to_schema(self, service):
        assert service.path_to_schema == os.path.join(
            config.SCHEMA_DIRECTORY, '%s.json' % service.id
        )

    def test_reader(self, service):
        assert service.schema.data == {'type': 'object'}
