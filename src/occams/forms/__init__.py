import logging
import pkg_resources

from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.i18n import TranslationStringFactory
from pyramid_who.whov2 import WhoV2AuthenticationPolicy
from sqlalchemy import orm
import zope.sqlalchemy
import wtforms_json

wtforms_json.init()  # monkey-patch wtforms to accept JSON data

import occams.datastore.models.events

__version__ = pkg_resources.require(__name__)[0].version

_ = TranslationStringFactory(__name__)

log = logging.getLogger(__name__)

Session = orm.scoped_session(orm.sessionmaker())

zope.sqlalchemy.register(Session)
occams.datastore.models.events.register(Session)

from .models import RootFactory, groupfinder


def main(global_config, **settings):
    """
    Returns initialized WSGI application
    """

    config = Configurator(
        settings=settings,
        root_factory=RootFactory,
        authentication_policy=WhoV2AuthenticationPolicy(
            settings.get('who.config_file'),
            settings.get('who.identifier_id'),
            groupfinder),
        authorization_policy=ACLAuthorizationPolicy())

    config.include('pyramid_chameleon')
    config.include('pyramid_redis_sessions')
    config.include('pyramid_rewrite')
    config.add_rewrite_rule(r'/(?P<path>.*)/', r'/%(path)s')
    config.include('pyramid_tm')

    config.include('.assets')
    config.include('.links')
    config.include('.models')
    config.include('.routes')

    config.scan()
    config.commit()

    app = config.make_wsgi_app()

    log.info('Ready')

    return app