from datetime import datetime

from elasticsearch_dsl import Search, query

import udata.core.contact_point.api_fields as contact_api_fields
import udata.core.dataset.api_fields as datasets_api_fields
from udata.api_fields import field, function_field, generate_fields
from udata.core.dataset.models import Dataset
from udata.core.elasticsearch import elasticsearch
from udata.core.metrics.models import WithMetrics
from udata.core.owned import Owned, OwnedQuerySet
from udata.i18n import lazy_gettext as _
from udata.models import Discussion, Follow, db
from udata.uris import endpoint_for

# "frequency"
# "harvest"
# "internal"
# "page"
# "quality" # Peut-être pas dans une v1 car la qualité sera probablement calculé différemment
# "datasets" # objet : liste de datasets liés à une API
# "spatial"
# "temporal_coverage"

DATASERVICE_FORMATS = ["REST", "WMS", "WSL"]


def build_search_query(query_text: str, score_functions):
    return query.Q(
        "bool",
        should=[
            query.Q(
                "function_score",
                query=query.Bool(
                    should=[
                        query.MultiMatch(
                            query=query_text,
                            type="phrase",
                            fields=["title^15", "acronym^15", "description^8"],
                        )
                    ]
                ),
                functions=score_functions,
            ),
            query.Q(
                "function_score",
                query=query.Bool(
                    should=[
                        query.MultiMatch(
                            query=query_text,
                            type="cross_fields",
                            fields=["title^7", "acronym^7", "description^4"],
                            operator="and",
                        )
                    ]
                ),
                functions=score_functions,
            ),
            query.Match(title={"query": query_text, "fuzziness": "AUTO:4,6"}),
        ],
    )


class DataserviceQuerySet(OwnedQuerySet):
    def visible(self):
        return self(archived_at=None, deleted_at=None, private=False)

    def hidden(self):
        return self(db.Q(private=True) | db.Q(deleted_at__ne=None) | db.Q(archived_at__ne=None))


@generate_fields()
class HarvestMetadata(db.EmbeddedDocument):
    backend = field(db.StringField())
    domain = field(db.StringField())

    source_id = field(db.StringField())
    source_url = field(db.URLField())

    remote_id = field(db.StringField())
    remote_url = field(db.URLField())

    # If the node ID is a `URIRef` it means it links to something external, if it's not an `URIRef` it's often a
    # auto-generated ID just to link multiple RDF node togethers. When exporting as RDF to other catalogs, we
    # want to re-use this node ID (only if it's not auto-generated) to improve compatibility.
    uri = field(
        db.URLField(),
        description="RDF node ID if it's an `URIRef`. `None` if it's not present or if it's a random auto-generated ID inside the graph.",
    )

    created_at = field(
        db.DateTimeField(), description="Date of the creation as provided by the harvested catalog"
    )
    last_update = field(db.DateTimeField(), description="Date of the last harvesting")
    archived_at = field(db.DateTimeField())


@generate_fields(searchable=True)
@elasticsearch(
    score_functions_description={
        "public_service_score": {"factor": 8, "modifier": "sqrt", "missing": 1},
        "metrics.followers": {"factor": 4, "modifier": "sqrt", "missing": 1},
        "metrics.views": {"factor": 1, "modifier": "sqrt", "missing": 1},
    },
    build_search_query=build_search_query,
    indexable=lambda dataservice: (
        not dataservice.archived_at and not dataservice.deleted_at and not dataservice.private
    ),
)
class Dataservice(WithMetrics, Owned, db.Document):
    meta = {
        "indexes": [
            "$title",
        ]
        + Owned.meta["indexes"],
        "queryset_class": DataserviceQuerySet,
        "auto_create_index_on_save": True,
    }

    title = field(
        db.StringField(required=True),
        example="My awesome API",
        sortable=True,
        searchable=True,
    )
    acronym = field(
        db.StringField(max_length=128),
        searchable=True,
    )
    # /!\ do not set directly the slug when creating or updating a dataset
    # this will break the search indexation
    slug = field(
        db.SlugField(
            max_length=255, required=True, populate_from="title", update=True, follow=True
        ),
        readonly=True,
    )
    description = field(
        db.StringField(default=""),
        description="In markdown",
        searchable=True,
    )
    base_api_url = field(
        db.URLField(required=True),
        sortable=True,
        searchable=True,
    )
    endpoint_description_url = field(
        db.URLField(),
        searchable=True,
    )
    authorization_request_url = field(
        db.URLField(),
        searchable=True,
    )
    availability = field(
        db.FloatField(min=0, max=100),
        example="99.99",
        searchable=True,
    )
    rate_limiting = field(db.StringField())
    is_restricted = field(
        db.BooleanField(),
        searchable=True,
    )
    has_token = field(
        db.BooleanField(),
        searchable=True,
    )
    format = field(
        db.StringField(choices=DATASERVICE_FORMATS),
        searchable=True,
    )

    license = field(
        db.ReferenceField("License"),
        allow_null=True,
        attribute="license.id",
        description="The ID of the license",
        searchable="keyword",
    )

    tags = field(
        db.TagListField(),
        searchable="keyword",
    )

    private = field(
        db.BooleanField(default=False),
        description="Is the dataservice private to the owner or the organization",
    )

    extras = field(db.ExtrasField())

    contact_point = field(
        db.ReferenceField("ContactPoint", reverse_delete_rule=db.NULLIFY),
        nested_fields=contact_api_fields.contact_point_fields,
        allow_null=True,
    )

    created_at = field(
        db.DateTimeField(verbose_name=_("Creation date"), default=datetime.utcnow, required=True),
        readonly=True,
        searchable=True,
    )
    metadata_modified_at = field(
        db.DateTimeField(
            verbose_name=_("Last modification date"), default=datetime.utcnow, required=True
        ),
        readonly=True,
        searchable=True,
    )
    deleted_at = field(db.DateTimeField(), readonly=True)
    archived_at = field(db.DateTimeField(), readonly=True)

    datasets = field(
        db.ListField(
            field(
                db.ReferenceField(Dataset),
                nested_fields=datasets_api_fields.dataset_ref_fields,
            )
        ),
        filterable={
            "key": "dataset",
        },
    )

    harvest = field(
        db.EmbeddedDocumentField(HarvestMetadata),
        readonly=True,
    )

    @function_field(description="Link to the API endpoint for this dataservice")
    def self_api_url(self):
        return endpoint_for("api.dataservice", dataservice=self, _external=True)

    @function_field(description="Link to the udata web page for this dataservice")
    def self_web_url(self):
        return endpoint_for("dataservices.show", dataservice=self, _external=True)

    # TODO
    # frequency = db.StringField(choices=list(UPDATE_FREQUENCIES.keys()))
    # temporal_coverage = db.EmbeddedDocumentField(db.DateRange)
    # spatial = db.EmbeddedDocumentField(SpatialCoverage)
    # harvest = db.EmbeddedDocumentField(HarvestDatasetMetadata)

    @property
    def is_hidden(self):
        return self.private or self.deleted_at or self.archived_at

    @function_field(indexable=True, api=False)
    def public_service_score(self):
        """
        Boolean `field_value_score` doesn't work well because False is 0 and `0*other_scores`
        always give a 0 score for the all query. So we set `4` and `1` for public service orgs.
        (`4` was choosen based on the value in `udata-search-service` but could maybe be `2` and
        then work with the `factor` of the `score_functions_description` definition.)
        """
        return 4 if (self.organization and self.organization.public_service) else 1

    def count_discussions(self):
        self.metrics["discussions"] = Discussion.objects(subject=self, closed=None).count()
        self.save()

    def count_followers(self):
        self.metrics["followers"] = Follow.objects(until=None).followers(self).count()
        self.save()
