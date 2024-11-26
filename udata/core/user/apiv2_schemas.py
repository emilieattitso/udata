from marshmallow import Schema, fields
from udata.api import BaseReferenceSchema
from udata.api.fields import MarshURLFor, MarshImageField, PaginationSchema
from udata.auth.helpers import current_user_is_admin_or_self

from .models import AVATAR_SIZES

BIGGEST_AVATAR_SIZE = AVATAR_SIZES[0]


class UserRefSchema(BaseReferenceSchema):
    first_name = fields.Str(dump_only=True)
    last_name = fields.Str(dump_only=True)
    slug = fields.Str(required=True)
    page = MarshURLFor(endpoint='users.show', mapper=lambda u: {'user': u}, fallback_endpoint='api.user', dump_only=True)
    uri = MarshURLFor(endpoint='api.user', mapper=lambda u: {'user': u}, dump_only=True)
    avatar = MarshImageField(dump_only=True)
    avatar_thumbnail = MarshImageField(dump_only=True, attribute='avatar', size=BIGGEST_AVATAR_SIZE)


from udata.core.organization.apiv2_schemas import OrganizationRefSchema  # noqa


class UserSchema(Schema):
    id = fields.Str(dump_only=True)
    first_name = fields.Str(dump_only=True)
    last_name = fields.Str(dump_only=True)
    slug = fields.Str(required=True)
    about = fields.Str()
    page = MarshURLFor(endpoint='users.show', mapper=lambda u: {'user': u}, fallback_endpoint='api.user', dump_only=True)
    uri = MarshURLFor(endpoint='api.user', mapper=lambda u: {'user': u}, dump_only=True)
    avatar = MarshImageField(dump_only=True)
    avatar_thumbnail = MarshImageField(dump_only=True, attribute='avatar', size=BIGGEST_AVATAR_SIZE)
    email = fields.Function(lambda obj: obj.email if current_user_is_admin_or_self() else None, dump_only=True)
    metrics = fields.Function(lambda obj: obj.get_metrics(), dump_only=True)
    active = fields.Boolean()
    roles = fields.List(fields.Str())
    created_at = fields.DateTime('%Y-%m-%dT%H:%M:%S+01:00', dump_only=True)
    organizations = fields.Nested(OrganizationRefSchema, many=True, dump_only=True)
    website = fields.Str()


class UserPaginationSchema(PaginationSchema):
    data = fields.List(fields.Nested(UserSchema), attribute="objects")