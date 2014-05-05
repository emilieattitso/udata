# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from flask import g, request

from udata.frontend import render
from udata.models import Topic
from udata.search import DatasetSearch, ReuseSearch, multisearch
from udata.i18n import I18nBlueprint
from udata.utils import multi_to_dict
# from udata.utils import get_by

blueprint = I18nBlueprint('topics', __name__, url_prefix='/topics')


class TopicSearch(object):
    def get_query(self):
        topic = self.kwargs['topic']
        must = []
        must.extend(self.build_text_queries())
        must.extend(self.build_facet_queries())
        must.extend(self.build_filters_queries())
        return {
            'bool': {
                'must': must,
                'should': [{'term': {'tags': tag}} for tag in topic.tags]
            }
        }


class DatasetTopicSearch(TopicSearch, DatasetSearch):
    pass


class ReuseTopicSearch(TopicSearch, ReuseSearch):
    pass


@blueprint.route('/<topic:topic>/')
def display(topic):
    kwargs = multi_to_dict(request.args)
    kwargs.update(topic=topic)

    datasets, reuses = multisearch(
        DatasetTopicSearch(**kwargs),
        ReuseTopicSearch(**kwargs),
    )

    return render('topic/display.html',
        topic=topic,
        datasets=datasets,
        reuses=reuses,
    )


@blueprint.before_app_request
def store_featured_topics():
    g.featured_topics = sorted(Topic.objects(featured=True), key=lambda t: t.slug)
