import json
import logging
import pathlib

import click
import requests
from flask import current_app

from udata.commands import cli
from udata.core.dataset.factories import (
    CommunityResourceFactory,
    DatasetFactory,
    ResourceFactory,
)
from udata.core.discussions.factories import DiscussionFactory, MessageDiscussionFactory
from udata.core.organization.factories import OrganizationFactory
from udata.core.organization.models import Member, Organization
from udata.core.reuse.factories import ReuseFactory
from udata.core.user.factories import UserFactory

log = logging.getLogger(__name__)


DATASET_URL = "/api/1/datasets"
ORG_URL = "/api/1/organizations"
REUSE_URL = "/api/1/reuses"
COMMUNITY_RES_URL = "/api/1/datasets/community_resources"
DISCUSSION_URL = "/api/1/discussions"


DEFAULT_FIXTURE_FILE: str = (
    "https://raw.githubusercontent.com/opendatateam/udata-fixtures/main/results.json"  # noqa
)
DEFAULT_FIXTURES_RESULTS_FILENAME: str = "results.json"


def fix_dates(obj: dict) -> dict:
    """Fix dates from the fixtures so they can be safely reloaded later on."""
    obj["created_at_internal"] = obj["internal"]["created_at_internal"]
    obj["last_modified_internal"] = obj["internal"]["last_modified_internal"]
    del obj["internal"]
    del obj["created_at"]


@cli.command()
@click.argument("data-source")
@click.argument("results-filename", default=DEFAULT_FIXTURES_RESULTS_FILENAME)
def generate_fixtures_file(data_source: str, results_filename: str) -> None:
    """Build sample fixture file based on datasets slugs list (users, datasets, reuses)."""
    results_file = pathlib.Path(results_filename)
    datasets_slugs = current_app.config["FIXTURE_DATASET_SLUGS"]
    json_result = []

    with click.progressbar(datasets_slugs) as bar:
        for slug in bar:
            json_fixture = {}

            json_dataset = requests.get(f"{data_source}{DATASET_URL}/{slug}/").json()
            del json_dataset["uri"]
            del json_dataset["page"]
            del json_dataset["last_update"]
            del json_dataset["last_modified"]
            del json_dataset["license"]
            del json_dataset["badges"]
            del json_dataset["spatial"]
            del json_dataset["quality"]
            fix_dates(json_dataset)
            json_resources = json_dataset.pop("resources")
            for res in json_resources:
                del res["latest"]
                del res["preview_url"]
                del res["last_modified"]
                fix_dates(res)
            if json_dataset["organization"] is None:
                json_owner = json_dataset.pop("owner")
                json_dataset["owner"] = json_owner["id"]
            else:
                json_org = json_dataset.pop("organization")
                json_org = requests.get(f"{data_source}{ORG_URL}/{json_org['id']}/").json()
                del json_org["members"]
                del json_org["page"]
                del json_org["uri"]
                del json_org["logo_thumbnail"]
                json_fixture["organization"] = json_org
            json_fixture["resources"] = json_resources
            json_fixture["dataset"] = json_dataset

            json_reuses = requests.get(
                f"{data_source}{REUSE_URL}/?dataset={json_dataset['id']}"
            ).json()["data"]
            for reuse in json_reuses:
                del reuse["datasets"]
                del reuse["image_thumbnail"]
                del reuse["page"]
                del reuse["uri"]
                del reuse["organization"]
                del reuse["owner"]
            json_fixture["reuses"] = json_reuses

            json_community = requests.get(
                f"{data_source}{COMMUNITY_RES_URL}/?dataset={json_dataset['id']}"
            ).json()["data"]
            for com in json_community:
                del com["dataset"]
                del com["organization"]
                del com["owner"]
                del com["latest"]
                del com["last_modified"]
                del com["preview_url"]
                fix_dates(com)
            json_fixture["community_resources"] = json_community

            json_discussion = requests.get(
                f"{data_source}{DISCUSSION_URL}/?for={json_dataset['id']}"
            ).json()["data"]
            for discussion in json_discussion:
                del discussion["subject"]
                del discussion["user"]
                del discussion["url"]
                del discussion["class"]
                for message in discussion["discussion"]:
                    del message["posted_by"]
            json_fixture["discussions"] = json_discussion

            json_result.append(json_fixture)

    with results_file.open("w") as f:
        json.dump(json_result, f, indent=2)
        print(f"Fixtures saved to file {results_filename}")


@cli.command()
@click.argument("source", default=DEFAULT_FIXTURE_FILE)
def generate_fixtures(source: str) -> None:
    """Build sample fixture data (users, datasets, reuses) from local or remote file."""
    if source.startswith("http"):
        json_fixtures = requests.get(source).json()
    else:
        with open(source) as f:
            json_fixtures = json.load(f)

    with click.progressbar(json_fixtures) as bar:
        for fixture in bar:
            user = UserFactory()
            if not fixture["organization"]:
                dataset = DatasetFactory(**fixture["dataset"], owner=user)
            else:
                org = Organization.objects(id=fixture["organization"]["id"]).first()
                if not org:
                    org = OrganizationFactory(
                        **fixture["organization"], members=[Member(user=user)]
                    )
                dataset = DatasetFactory(**fixture["dataset"], organization=org)
            for resource in fixture["resources"]:
                res = ResourceFactory(**resource)
                dataset.add_resource(res)
            for reuse in fixture["reuses"]:
                ReuseFactory(**reuse, datasets=[dataset], owner=user)
            for community in fixture["community_resources"]:
                CommunityResourceFactory(**community, dataset=dataset, owner=user)
            for discussion in fixture["discussions"]:
                messages = discussion.pop("discussion")
                DiscussionFactory(
                    **discussion,
                    subject=dataset,
                    user=user,
                    discussion=[
                        MessageDiscussionFactory(**message, posted_by=user) for message in messages
                    ],
                )
