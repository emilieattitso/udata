import pytest

from datetime import datetime

from udata.core.dataset.factories import DatasetFactory
from udata.features.webhooks.tasks import dispatch, _dispatch
from udata.features.webhooks.utils import sign

pytestmark = pytest.mark.usefixtures('clean_db')


class WebhookUnitTest():

    @pytest.mark.options(WEBHOOKS=[])
    def test_no_webhooks(self):
        dispatch('event', {})
        assert True

    def test_webhooks_task(self, rmock):
        '''NB: apparently celery task errors don't surface so we need to test them directly'''
        r = rmock.post('https://example.com', text='ok', status_code=200)
        _dispatch('event', {'tada': 'dam'}, {
            'url': 'https://example.com',
            'secret': 'mysecret',
        })
        assert r.called
        assert r.call_count == 1
        res = r.last_request
        payload = {
            'event': 'event',
            'payload': {'tada': 'dam'},
        }
        assert res.headers.get('x-hook-signature') == sign(payload, 'mysecret')
        assert res.json() == payload

    @pytest.mark.options(WEBHOOKS=[{
        'url': 'https://example.com/1',
        'events': ['event'],
        'secret': 'mysecret',
    }, {
        'url': 'https://example.com/2',
        'events': ['event'],
        'secret': 'mysecret',
    }, {
        'url': 'https://example.com/3',
        'events': ['notmyevent'],
        'secret': 'mysecret',
    }])
    def test_webhooks_from_settings(self, rmock):
        r1 = rmock.post('https://example.com/1', text='ok', status_code=200)
        r2 = rmock.post('https://example.com/2', text='ok', status_code=200)
        r3 = rmock.post('https://example.com/3', text='ok', status_code=200)
        dispatch('event', {})
        assert r1.called
        assert r1.call_count == 1
        assert r2.called
        assert r2.call_count == 1
        assert not r3.called

    @pytest.mark.skip(reason="""
        I really tried but no luck :-(
        (pytest-celery, using requests Retry instead of Celery's...)
        Made it work in real life on 2021-06-18 (true story)
    """)
    @pytest.mark.options(WEBHOOKS=[{
        'url': 'https://example.com/3',
        'secret': 'mysecret',
    }])
    def test_webhooks_retry(self, rmock):
        r = rmock.post('https://example.com/3', text='ko', status_code=500)
        dispatch('event', {'tada': 'dam'})
        assert r.called
        assert r.call_count == 3


@pytest.mark.options(WEBHOOKS=[{
    'url': 'https://example.com/publish',
    'events': [
        'datagouvfr.dataset.created',
        'datagouvfr.dataset.updated',
        'datagouvfr.dataset.deleted',
    ],
    'secret': 'mysecret',
}])
class WebhookIntegrationTest():
    modules = []
    # plug the signals in for tests
    from udata.features.webhooks import triggers  # noqa

    @pytest.fixture
    def rmock_pub(self, rmock):
        return rmock.post('https://example.com/publish', text='ok', status_code=201)

    def test_dataset_create(self, rmock_pub):
        ds = DatasetFactory()
        assert rmock_pub.called
        res = rmock_pub.last_request.json()
        assert res['event'] == 'datagouvfr.dataset.created'
        assert res['payload']['title'] == ds['title']

    def test_dataset_update(self, rmock_pub):
        ds = DatasetFactory()
        ds.title = 'newtitle'
        ds.save()
        assert rmock_pub.called
        res = rmock_pub.last_request.json()
        assert res['event'] == 'datagouvfr.dataset.updated'
        assert res['payload']['title'] == 'newtitle'

    def test_dataset_delete(self, rmock_pub):
        ds = DatasetFactory()
        ds.deleted = datetime.now()
        ds.save()
        assert rmock_pub.called
        res = rmock_pub.last_request.json()
        assert res['event'] == 'datagouvfr.dataset.deleted'
        assert res['payload']['title'] == ds['title']
