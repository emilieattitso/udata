import random
import string
import time

from elasticsearch_dsl import analyzer, token_filter, tokenizer
from flask import url_for

from udata.core.badges.models import Badge
from udata.core.dataservices.factories import DataserviceFactory
from udata.core.dataservices.models import Dataservice
from udata.core.dataset.factories import DatasetFactory, LicenseFactory
from udata.core.organization.constants import CERTIFIED, PUBLIC_SERVICE
from udata.core.organization.factories import OrganizationFactory
from udata.core.organization.models import Member, Organization
from udata.core.user.factories import UserFactory
from udata.i18n import gettext as _

from . import APITestCase


class DataserviceAPITest(APITestCase):
    modules = []

    def test_dataservice_api_create(self):
        user = self.login()
        datasets = DatasetFactory.create_batch(3)
        license = LicenseFactory.create()

        response = self.post(
            url_for("api.dataservices"),
            {
                "title": "My API",
                "base_api_url": "https://example.org",
            },
        )
        self.assert201(response)
        self.assertEqual(Dataservice.objects.count(), 1)

        dataservice = Dataservice.objects.first()

        response = self.get(url_for("api.dataservice", dataservice=dataservice))
        self.assert200(response)

        self.assertEqual(response.json["title"], "My API")
        self.assertEqual(response.json["base_api_url"], "https://example.org")
        self.assertEqual(response.json["owner"]["id"], str(user.id))

        response = self.patch(
            url_for("api.dataservice", dataservice=dataservice),
            {
                "title": "Updated title",
                "tags": ["hello", "world"],
                "private": True,
                "datasets": [datasets[0].id, datasets[2].id],
                "license": license.id,
                "extras": {
                    "foo": "bar",
                },
            },
        )
        self.assert200(response)

        self.assertEqual(response.json["title"], "Updated title")
        self.assertEqual(response.json["base_api_url"], "https://example.org")
        self.assertEqual(response.json["tags"], ["hello", "world"])
        self.assertEqual(response.json["private"], True)
        self.assertEqual(response.json["datasets"][0]["title"], datasets[0].title)
        self.assertEqual(response.json["datasets"][1]["title"], datasets[2].title)
        self.assertEqual(
            response.json["extras"],
            {
                "foo": "bar",
            },
        )
        self.assertEqual(response.json["license"], license.id)
        self.assertEqual(
            response.json["self_api_url"], "http://local.test/api/1/dataservices/updated-title/"
        )
        dataservice.reload()
        self.assertEqual(dataservice.title, "Updated title")
        self.assertEqual(dataservice.base_api_url, "https://example.org")
        self.assertEqual(dataservice.tags, ["hello", "world"])
        self.assertEqual(dataservice.private, True)
        self.assertEqual(dataservice.datasets[0].title, datasets[0].title)
        self.assertEqual(dataservice.datasets[1].title, datasets[2].title)
        self.assertEqual(
            dataservice.extras,
            {
                "foo": "bar",
            },
        )
        self.assertEqual(dataservice.license.title, license.title)
        self.assertEqual(
            dataservice.self_api_url(), "http://local.test/api/1/dataservices/updated-title/"
        )

        response = self.delete(url_for("api.dataservice", dataservice=dataservice))
        self.assert204(response)

        self.assertEqual(Dataservice.objects.count(), 1)

        dataservice.reload()
        self.assertEqual(dataservice.title, "Updated title")
        self.assertEqual(dataservice.base_api_url, "https://example.org")
        self.assertIsNotNone(dataservice.deleted_at)

        # response = self.get(url_for('api.dataservice', dataservice=dataservice))
        # self.assert410(response)

    def test_dataservice_api_index(self):
        dataset_a = DatasetFactory()
        dataset_b = DatasetFactory()

        self.login()
        self.post(
            url_for("api.dataservices"),
            {
                "title": "B",
                "base_api_url": "https://example.org/B",
                "datasets": [dataset_b.id],
            },
        )
        self.post(
            url_for("api.dataservices"),
            {
                "title": "C",
                "base_api_url": "https://example.org/C",
                "datasets": [dataset_a.id, dataset_b.id],
            },
        )
        self.post(
            url_for("api.dataservices"),
            {
                "title": "A",
                "base_api_url": "https://example.org/A",
                "datasets": [dataset_a.id],
            },
        )
        self.post(
            url_for("api.dataservices"),
            {
                "title": "X",
                "base_api_url": "https://example.org/X",
                "private": True,
                "datasets": [dataset_a.id],
            },
        )

        self.assertEqual(Dataservice.objects.count(), 4)

        response = self.get(url_for("api.dataservices"))
        self.assert200(response)

        self.assertEqual(response.json["previous_page"], None)
        self.assertEqual(response.json["next_page"], None)
        self.assertEqual(response.json["page"], 1)
        self.assertEqual(response.json["total"], 3)
        self.assertEqual(len(response.json["data"]), 3)
        self.assertEqual(response.json["data"][0]["title"], "B")
        self.assertEqual(response.json["data"][0]["datasets"][0]["id"], str(dataset_b.id))
        self.assertEqual(response.json["data"][1]["title"], "C")
        self.assertEqual(response.json["data"][1]["datasets"][0]["id"], str(dataset_a.id))
        self.assertEqual(response.json["data"][1]["datasets"][1]["id"], str(dataset_b.id))
        self.assertEqual(response.json["data"][2]["title"], "A")
        self.assertEqual(response.json["data"][2]["datasets"][0]["id"], str(dataset_a.id))

        response = self.get(url_for("api.dataservices", sort="title"))
        self.assert200(response)

        self.assertEqual(response.json["previous_page"], None)
        self.assertEqual(response.json["next_page"], None)
        self.assertEqual(response.json["page"], 1)
        self.assertEqual(response.json["total"], 3)
        self.assertEqual(len(response.json["data"]), 3)
        self.assertEqual(response.json["data"][0]["title"], "A")
        self.assertEqual(response.json["data"][1]["title"], "B")
        self.assertEqual(response.json["data"][2]["title"], "C")

        response = self.get(url_for("api.dataservices", sort="-title"))
        self.assert200(response)

        self.assertEqual(response.json["previous_page"], None)
        self.assertEqual(response.json["next_page"], None)
        self.assertEqual(response.json["page"], 1)
        self.assertEqual(response.json["total"], 3)
        self.assertEqual(len(response.json["data"]), 3)
        self.assertEqual(response.json["data"][0]["title"], "C")
        self.assertEqual(response.json["data"][1]["title"], "B")
        self.assertEqual(response.json["data"][2]["title"], "A")

        response = self.get(url_for("api.dataservices", page_size=1))
        self.assert200(response)

        self.assertEqual(response.json["previous_page"], None)
        assert response.json["next_page"].endswith(url_for("api.dataservices", page_size=1, page=2))
        self.assertEqual(response.json["page"], 1)
        self.assertEqual(response.json["total"], 3)
        self.assertEqual(len(response.json["data"]), 1)
        self.assertEqual(response.json["data"][0]["title"], "B")

        response = self.get(url_for("api.dataservices", sort="title", dataset=str(dataset_a.id)))
        self.assert200(response)

        self.assertEqual(response.json["total"], 2)
        self.assertEqual(response.json["data"][0]["title"], "A")
        self.assertEqual(response.json["data"][0]["datasets"][0]["id"], str(dataset_a.id))
        self.assertEqual(response.json["data"][1]["title"], "C")
        self.assertEqual(response.json["data"][1]["datasets"][0]["id"], str(dataset_a.id))
        self.assertEqual(response.json["data"][1]["datasets"][1]["id"], str(dataset_b.id))

    def test_dataservice_api_index_with_wrong_dataset_id(self):
        response = self.get(url_for("api.dataservices", sort="title", dataset=str("xxx")))
        self.assert400(response)

    def test_dataservice_api_create_with_validation_error(self):
        self.login()
        response = self.post(
            url_for("api.dataservices"),
            {
                "base_api_url": "https://example.org",
            },
        )
        self.assert400(response)
        self.assertEqual(Dataservice.objects.count(), 0)

    def test_dataservice_api_create_with_unkwown_license(self):
        self.login()
        response = self.post(
            url_for("api.dataservices"),
            {
                "title": "My title",
                "base_api_url": "https://example.org",
                "license": "unwkown-license",
            },
        )
        self.assert400(response)
        self.assertEqual(
            response.json["errors"]["license"], ["Unknown reference 'unwkown-license'"]
        )
        self.assertEqual(Dataservice.objects.count(), 0)

    def test_dataservice_api_create_with_unkwown_contact_point(self):
        self.login()

        response = self.post(
            url_for("api.dataservices"),
            {
                "title": "My title",
                "base_api_url": "https://example.org",
                "contact_point": "66212433e42ab56639ad516e",
            },
        )
        self.assert400(response)
        self.assertEqual(
            response.json["errors"]["contact_point"],
            ["Unknown reference '66212433e42ab56639ad516e'"],
        )
        self.assertEqual(Dataservice.objects.count(), 0)

    def test_dataservice_api_create_with_custom_user_or_org(self):
        other = UserFactory()
        other_member = Member(user=other, role="editor")
        other_org = OrganizationFactory(members=[other_member])

        me = self.login()
        me_member = Member(user=me, role="editor")
        me_org = OrganizationFactory(members=[me_member])

        response = self.post(
            url_for("api.dataservices"),
            {
                "title": "My title",
                "base_api_url": "https://example.org",
                "owner": other.id,
            },
        )
        self.assert400(response)
        self.assertEqual(
            response.json["errors"]["owner"], [_("You can only set yourself as owner")]
        )
        self.assertEqual(Dataservice.objects.count(), 0)

        response = self.post(
            url_for("api.dataservices"),
            {
                "title": "My title",
                "base_api_url": "https://example.org",
                "organization": other_org.id,
            },
        )
        self.assert400(response)
        self.assertEqual(
            response.json["errors"]["organization"], [_("Permission denied for this organization")]
        )
        self.assertEqual(Dataservice.objects.count(), 0)

        response = self.post(
            url_for("api.dataservices"),
            {
                "title": "My title",
                "base_api_url": "https://example.org",
                "owner": me.id,
            },
        )
        self.assert201(response)
        dataservice = Dataservice.objects(id=response.json["id"]).first()
        self.assertEqual(dataservice.owner.id, me.id)
        self.assertEqual(dataservice.organization, None)

        response = self.post(
            url_for("api.dataservices"),
            {
                "title": "My title",
                "base_api_url": "https://example.org",
                "organization": me_org.id,
            },
        )
        self.assert201(response)
        dataservice = Dataservice.objects(id=response.json["id"]).first()
        self.assertEqual(dataservice.owner, None)
        self.assertEqual(dataservice.organization.id, me_org.id)

    def test_elasticsearch(self):
        orga_sp = OrganizationFactory(badges=[Badge(kind=CERTIFIED), Badge(kind=PUBLIC_SERVICE)])
        orga_unknown = OrganizationFactory()
        assert orga_sp.public_service
        assert not orga_unknown.public_service

        dataservice_a = DataserviceFactory(
            organization=orga_unknown,
            title="A - Hello AMD world!",
            metrics={
                "followers": 42,
                "views": 1337,
            },
        )
        dataservice_b = DataserviceFactory(
            organization=orga_unknown,
            title="B - Other one",
            metrics={
                "followers": 1337,
                "views": 1000,
            },
        )
        dataservice_c = DataserviceFactory(
            organization=orga_unknown,
            title="C - AMD",
            metrics={
                "followers": 41,
                "views": 1345,
            },
        )
        time.sleep(1)

        dataservices = Dataservice.__elasticsearch_search__("AMDAC")

        assert len(dataservices) == 2
        assert dataservices[0].title == dataservice_c.title
        assert dataservices[1].title == dataservice_a.title

        dataservice_b.title = "B - Hello AMD world!"
        dataservice_b.save()
        time.sleep(3)

        dataservices = Dataservice.__elasticsearch_search__("AMDAC")

        assert len(dataservices) == 3

        # `dataservice_b` should be first because it has a lot of followers
        assert dataservices[0].title == dataservice_b.title
        assert dataservices[1].title == dataservice_c.title
        assert dataservices[2].title == dataservice_a.title

        dataservice_a.organization = orga_sp
        dataservice_a.save()
        assert dataservice_a.public_service_score() == 4
        time.sleep(3)

        dataservices = Dataservice.__elasticsearch_search__("AMDAC")

        assert len(dataservices) == 3

        # `dataservice_b` should be first because it has a lot of followers
        assert dataservices[0].title == dataservice_b.title
        assert dataservices[1].title == dataservice_a.title
        assert dataservices[2].title == dataservice_c.title
