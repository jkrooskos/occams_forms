import json

from pyramid.session import check_csrf_token
from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest
import sqlalchemy as sa
from sqlalchemy import orm
import wtforms

from occams.utils.forms import Form
from occams_datastore import models as datastore

from .. import _
from ._utils import jquery_wtform_validator


@view_config(
    route_name='forms.index',
    permission='view',
    renderer='../templates/form/list.pt')
def list_(request):
    return {}


@view_config(
    route_name='forms.index',
    permission='view',
    xhr=True,
    renderer='json')
def list_json(context, request):
    """
    Lists all forms used by instance.
    """
    return get_list_data(request)


@view_config(
    route_name='forms.index',
    permission='add',
    request_method='POST',
    request_param='files',
    xhr=True,
    renderer='json')
def upload(context, request):
    """
    Allows the user to upload a JSON file form.
    """
    check_csrf_token(request)

    db_session = request.db_session

    files = request.POST.getall('files')

    if len(files) < 1:
        raise HTTPBadRequest(json={
            'user_message': _(u'Nothing uploaded')})

    schemata = [datastore.Schema.from_json(json.load(u.file)) for u in files]
    db_session.add_all(schemata)
    db_session.flush()

    return get_list_data(request, names=[s.name for s in schemata])


@view_config(
    route_name='forms.index',
    permission='add',
    xhr=True,
    request_param='validate',
    renderer='json')
def validate_value_json(context, request):
    FormForm = FormFormFactory(context, request)
    return jquery_wtform_validator(FormForm, context, request)


@view_config(
    route_name='forms.index',
    permission='add',
    request_method='POST',
    xhr=True,
    renderer='json')
def add(context, request):
    """
    Allows a user to create a new type of form.
    """
    check_csrf_token(request)

    db_session = request.db_session

    FormForm = FormFormFactory(context, request)

    form = FormForm.from_json(request.json_body)

    if not form.validate():
        raise HTTPBadRequest(json={'errors': form.errors})

    schema = datastore.Schema(**form.data)
    db_session.add(schema)
    db_session.flush()

    return get_list_data(request, names=[schema.name])['forms'][0]


def get_list_data(request, names=None):
    db_session = request.db_session
    InnerSchema = orm.aliased(datastore.Schema)
    InnerAttribute = orm.aliased(datastore.Attribute)
    query = (
        db_session.query(datastore.Schema.name)
        .add_column(
            db_session.query(
                db_session.query(InnerAttribute)
                .join(InnerSchema, InnerAttribute.schema)
                .filter(InnerSchema.name == datastore.Schema.name)
                .filter(InnerAttribute.is_private)
                .correlate(datastore.Schema)
                .exists())
            .as_scalar()
            .label('has_private'))
        .add_column(
            db_session.query(InnerSchema.title)
            .filter(InnerSchema.name == datastore.Schema.name)
            .order_by(
                InnerSchema.publish_date == sa.null(),
                InnerSchema.publish_date.desc())
            .limit(1)
            .correlate(datastore.Schema)
            .as_scalar()
            .label('title'))
        .group_by(datastore.Schema.name)
        .order_by(datastore.Schema.name))

    if names:
        query = query.filter(datastore.Schema.name.in_(names))

    def jsonify(row):
        values = row._asdict()
        versions = (
            db_session.query(datastore.Schema)
            .filter(datastore.Schema.name == row.name)
            .order_by(datastore.Schema.publish_date == sa.null(),
                      datastore.Schema.publish_date.desc()))
        values['versions'] = [{
            '__url__':  request.route_path(
                'forms.version',
                form=row.name,
                version=version.publish_date or version.id),
            'id': version.id,
            'name': version.name,
            'title': version.title,
            'publish_date': version.publish_date and str(version.publish_date),
            'retract_date': version.retract_date and str(version.retract_date)
        } for version in versions]
        return values

    return {
        'forms': [jsonify(r) for r in query]
    }


def FormFormFactory(context, request):
    db_session = request.db_session

    def check_unique_name(form, field):
        (exists,) = (
            db_session.query(
                db_session.query(datastore.Schema)
                .filter_by(name=field.data.lower())
                .exists())
            .one())
        if exists:
            raise wtforms.ValidationError(_(u'Form name already in use'))

    class FormForm(Form):

        name = wtforms.StringField(
            validators=[
                wtforms.validators.InputRequired(),
                wtforms.validators.Length(min=3, max=100),
                wtforms.validators.Regexp('^[a-zA-Z_][a-zA-Z0-9_]+$'),
                check_unique_name])

        title = wtforms.StringField(
            validators=[
                wtforms.validators.InputRequired(),
                wtforms.validators.Length(min=3, max=128)])

    return FormForm
