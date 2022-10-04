'''
Datasets linked to an inactive harvester are archived
'''
import logging

from udata.models import Dataset
from udata.harvest.actions import archive_harvested_dataset
from udata.harvest.models import HarvestSource


log = logging.getLogger(__name__)


def migrate(db):
    log.info('Computing the list of datasets linked to an inactive harvester.')

    active_sources = [str(source.id) for source in HarvestSource.objects(active=True)]
    dangling_datasets = Dataset.objects(**{
        'extras__harvest:source_id__exists': True,
        'extras__harvest:source_id__nin': active_sources,
        'archived': None
    })

    log.info(f'{dangling_datasets.count()} datasets to archive.')

    for dataset in dangling_datasets:
        archive_harvested_dataset(dataset, reason='harvester-inactive', dryrun=False)

    log.info('Done')